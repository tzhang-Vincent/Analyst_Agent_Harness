"""Run the evaluation in either mode:

- **pipeline** (default): deterministic orchestration + LLM at fixed steps
  (LLM intent parsing -> deterministic extraction -> LLM summary -> verifier).
  Reports *intent accuracy* (did the LLM parse the right tickers/metrics?).
- **agent**: the LLM drives data retrieval through tool calls, then summarizes.
  Reports *coverage/precision* (did its tool calls fetch the right data?).

Both modes measure: coverage (recall), precision, provenance, and the number of
unsupported numeric claims the verifier caught and removed ("hallucinations").

The bare-LLM baseline (same model, no harness) is reported for comparison.

Run::

    python -m eval.run_eval                        # pipeline (full harness)
    python -m eval.run_eval --mode agent           # agentic tool loop
    python -m eval.run_eval --baseline --limit 5   # + bare-LLM, quick subset
"""

from __future__ import annotations

import argparse

from rich.console import Console
from rich.table import Table

from agent.analyst import Analyst
from agent.edgar import EdgarClient
from agent.llm import LLM, is_configured
from agent.profile import Memory
from agent.verifier import extract_numbers

from .dialogues import DIALOGUES
from .ground_truth import build_oracle
from .questions import QUESTIONS
from .report import EvalRow, provenance_coverage, summarize, value_coverage, value_precision

console = Console()


def _baseline_answer(llm: LLM, question: str) -> list[float]:
    system = (
        "You are a financial analyst. Answer the question with specific dollar "
        "amounts. Do not use any tools, and do not say you lack data — answer "
        "from your own knowledge."
    )
    resp = llm.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": question}]
    )
    return extract_numbers(resp.get("content") or "")


def _intent_ok(intent, q) -> bool:
    """Did the parsed intent match the question's ground-truth spec exactly?"""
    if intent is None:
        return False
    return (
        set(intent.tickers) == set(q.tickers)
        and set(intent.metrics) == set(q.metrics)
        and intent.frequency == q.frequency
        and intent.num_periods == q.n
    )


def _run_dialogues(llm: LLM | None) -> None:
    """Multi-turn conversation eval: per-turn coverage/precision/provenance/hallucination.

    Reference resolution is measured indirectly: a turn's oracle encodes the
    *correct* resolution (e.g. "compare it with AMD" -> ["NVDA", "AMD"]), so a
    mis-resolved reference fetches the wrong data and drops coverage/precision.
    """
    if llm is None:
        console.print("[red]--chat needs an LLM key.[/red]")
        return

    covs: list[float] = []
    precs: list[float] = []
    provs: list[float] = []
    hallus: list[int] = []
    resolved = 0
    total = 0

    with EdgarClient() as client:
        analyst = Analyst(client=client, memory=Memory("data/eval_memory"), llm=llm, mode="agent")
        for dialogue in DIALOGUES:
            history: list[dict] = []
            for i, turn in enumerate(dialogue.turns, 1):
                answer = analyst.run(turn.text, history=history)
                oracle_values = [o.value for o in build_oracle(client, turn)]
                values = [f.provenance.value for f in answer.facts]
                hcov = value_coverage(values, oracle_values)
                hprec = value_precision(values, oracle_values)
                prov = provenance_coverage(answer.facts)
                halluc = answer.summary.count("[unverified]")
                covs.append(hcov)
                precs.append(hprec)
                provs.append(prov)
                hallus.append(halluc)
                total += 1
                if hcov >= 1.0 and hprec >= 1.0:
                    resolved += 1
                print(
                    f"[{dialogue.id} t{i}] coverage={hcov * 100:.0f}% "
                    f"precision={hprec * 100:.0f}% prov={prov * 100:.0f}% halluc={halluc}",
                    flush=True,
                )
                history.append({"role": "user", "content": turn.text})
                history.append({"role": "assistant", "content": answer.summary})

    console.print(
        f"\n[b]Dialogue summary[/b]: {total} turns — "
        f"coverage {sum(covs) / total * 100:.0f}%, "
        f"precision {sum(precs) / total * 100:.0f}%, "
        f"provenance {sum(provs) / total * 100:.0f}%, "
        f"hallucinations {sum(hallus)}, "
        f"reference-resolved turns {resolved}/{total} ({resolved / total * 100:.0f}%)"
    )


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", action="store_true",
                   help="also run the bare-LLM baseline (requires an LLM key).")
    p.add_argument("--limit", type=int, default=None,
                   help="run only the first N questions.")
    p.add_argument("--mode", choices=["pipeline", "agent"], default="pipeline",
                   help="pipeline = deterministic orchestration; agent = LLM tool loop.")
    p.add_argument("--no-llm-intent", action="store_true",
                   help="(pipeline only) use rule intent parsing instead of the LLM.")
    p.add_argument("--chat", action="store_true",
                   help="run the multi-turn conversation eval (agent mode).")
    p.add_argument("--provider", choices=["anthropic", "openai", "deepseek"])
    p.add_argument("--model")
    args = p.parse_args(argv)

    llm: LLM | None = LLM(args.provider, args.model) if is_configured(args.provider) else None
    if llm is None:
        console.print("[yellow]No LLM key configured; harness runs deterministic (no LLM).[/yellow]")

    if args.chat:
        _run_dialogues(llm)
        return

    questions = QUESTIONS if args.limit is None else QUESTIONS[: args.limit]
    show_intent = args.mode == "pipeline"

    rows: list[EvalRow] = []
    with EdgarClient() as client:
        analyst = Analyst(
            client=client,
            memory=Memory("data/eval_memory"),
            llm=llm,
            use_llm_intent=not args.no_llm_intent,
            mode=args.mode,
        )
        for q in questions:
            oracle = build_oracle(client, q)
            oracle_values = [o.value for o in oracle]

            answer = analyst.run(q.text)
            values = [f.provenance.value for f in answer.facts]
            iok = _intent_ok(analyst.last_intent, q) if show_intent else None
            if q.open_ended:
                hcov = hprec = None  # no single "correct" spec; only provenance+hallucination matter
            else:
                hcov = value_coverage(values, oracle_values)
                hprec = value_precision(values, oracle_values)
            prov = provenance_coverage(answer.facts)
            halluc = answer.summary.count("[unverified]")

            bcov = None
            if args.baseline and llm is not None:
                bcov = value_coverage(_baseline_answer(llm, q.text), oracle_values)

            rows.append(
                EvalRow(q.id, q.category, len(oracle_values), iok, hcov, prov, hprec, halluc, bcov)
            )
            cov_str = f"coverage={hcov * 100:.0f}% precision={hprec * 100:.0f}%" if hcov is not None else "(open-ended)"
            line = (
                f"[{q.id}] {cov_str} prov={prov * 100:.0f}% halluc={halluc}"
                + (f" bare_llm={bcov * 100:.0f}%" if bcov is not None else "")
            )
            print(line, flush=True)

    table = Table(title=f"Evaluation ({args.mode} mode)")
    table.add_column("Q", justify="right")
    table.add_column("Category")
    table.add_column("Oracle", justify="right")
    if show_intent:
        table.add_column("Intent", justify="right")
    table.add_column("Coverage", justify="right")
    table.add_column("Precision", justify="right")
    table.add_column("Provenance", justify="right")
    table.add_column("Halluc.", justify="right")
    if args.baseline and llm is not None:
        table.add_column("Bare LLM", justify="right")
    for r in rows:
        row = [r.question_id, r.category, str(r.oracle_values)]
        if show_intent:
            row.append("ok" if r.intent_ok else "BAD")
        row += [
            f"{r.harness_coverage * 100:.0f}%" if r.harness_coverage is not None else "—",
            f"{r.harness_precision * 100:.0f}%" if r.harness_precision is not None else "—",
            f"{r.harness_provenance * 100:.0f}%", str(r.hallucinations),
        ]
        if args.baseline and llm is not None:
            row.append(f"{r.baseline_coverage * 100:.0f}%" if r.baseline_coverage is not None else "—")
        table.add_row(*row)
    console.print(table)

    s = summarize(rows)
    parts = []
    if s["intent_accuracy"] is not None:
        parts.append(f"intent [green]{s['intent_accuracy'] * 100:.0f}%[/green]")
    if s["harness_accuracy"] is not None:
        parts.append(f"coverage [green]{s['harness_accuracy'] * 100:.0f}%[/green]")
    if s["harness_precision"] is not None:
        parts.append(f"precision [green]{s['harness_precision'] * 100:.0f}%[/green]")
    parts += [
        f"provenance [green]{s['harness_provenance'] * 100:.0f}%[/green]",
        f"hallucinations caught [green]{s['hallucinations']}[/green]",
    ]
    if s["baseline_accuracy"] is not None:
        parts.append(f"bare-LLM coverage [red]{s['baseline_accuracy'] * 100:.0f}%[/red]")
    console.print(f"\n[b]Overall[/b]: {s['questions']} questions — " + ", ".join(parts))


if __name__ == "__main__":
    main()
