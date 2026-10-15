"""Run the evaluation.

The **harness is measured as the full product** — ``Analyst`` with the LLM wired
in, i.e. intent parsing + deterministic EDGAR extraction + LLM summary + the
verifier gate. Metrics on the final answer:

- **coverage (recall)** — fraction of EDGAR-oracle values present in the answer.
- **precision** — fraction of the answer's values that are actually in the oracle
  (catches wrong/extra companies or metrics).
- **provenance** — fraction of facts carrying a filing link.
- **hallucinations** — number of unsupported numbers the verifier caught and
  removed from the LLM-written summary (0 = the LLM stayed within the facts).

The **bare-LLM baseline** is the same model with no harness, forced to answer
from memory — the "ChatGPT" equivalent.

Run::

    python -m eval.run_eval              # full harness (LLM summary if a key is set)
    python -m eval.run_eval --baseline   # also the bare-LLM baseline
"""

from __future__ import annotations

import argparse

from rich.console import Console
from rich.table import Table

from agent.agent import Analyst
from agent.edgar import EdgarClient
from agent.llm import LLM, is_configured
from agent.profile import Memory
from agent.verifier import extract_numbers

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


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", action="store_true",
                   help="also run the bare-LLM baseline (requires an LLM key).")
    p.add_argument("--limit", type=int, default=None,
                   help="run only the first N questions.")
    p.add_argument("--provider", choices=["anthropic", "openai", "deepseek"])
    p.add_argument("--model")
    args = p.parse_args(argv)

    llm: LLM | None = LLM(args.provider, args.model) if is_configured(args.provider) else None
    if llm is None:
        console.print("[yellow]No LLM key configured; harness runs deterministic (no LLM summary).[/yellow]")

    questions = QUESTIONS if args.limit is None else QUESTIONS[: args.limit]

    rows: list[EvalRow] = []
    with EdgarClient() as client:
        # use_llm_intent=False keeps intent parsing deterministic so coverage/
        # precision measure the data layer (not the LLM's intent parse), while
        # the LLM is still used for the summary, whose hallucinations are counted.
        analyst = Analyst(
            client=client, memory=Memory("data/eval_memory"), llm=llm, use_llm_intent=False
        )
        for q in questions:
            oracle = build_oracle(client, q)
            oracle_values = [o.value for o in oracle]

            answer = analyst.run(q.text)
            values = [f.provenance.value for f in answer.facts]
            hcov = value_coverage(values, oracle_values)
            hprec = value_precision(values, oracle_values)
            prov = provenance_coverage(answer.facts)
            halluc = answer.summary.count("[unverified]")

            bcov = None
            if args.baseline and llm is not None:
                bcov = value_coverage(_baseline_answer(llm, q.text), oracle_values)

            rows.append(
                EvalRow(q.id, q.category, len(oracle_values), hcov, prov, hprec, halluc, bcov)
            )
            line = (
                f"[{q.id}] coverage={hcov * 100:.0f}% precision={hprec * 100:.0f}% "
                f"prov={prov * 100:.0f}% halluc={halluc}"
                + (f" bare_llm={bcov * 100:.0f}%" if bcov is not None else "")
            )
            print(line, flush=True)

    table = Table(title="Evaluation (full harness, with LLM)")
    table.add_column("Q", justify="right")
    table.add_column("Category")
    table.add_column("Oracle", justify="right")
    table.add_column("Coverage", justify="right")
    table.add_column("Precision", justify="right")
    table.add_column("Provenance", justify="right")
    table.add_column("Halluc.", justify="right")
    if args.baseline and llm is not None:
        table.add_column("Bare LLM", justify="right")
    for r in rows:
        row = [
            r.question_id, r.category, str(r.oracle_values),
            f"{r.harness_coverage * 100:.0f}%", f"{r.harness_precision * 100:.0f}%",
            f"{r.harness_provenance * 100:.0f}%", str(r.hallucinations),
        ]
        if args.baseline and llm is not None:
            row.append(f"{r.baseline_coverage * 100:.0f}%" if r.baseline_coverage is not None else "—")
        table.add_row(*row)
    console.print(table)

    s = summarize(rows)
    console.print(
        f"\n[b]Overall[/b]: {s['questions']} questions — "
        f"coverage [green]{s['harness_accuracy'] * 100:.0f}%[/green], "
        f"precision [green]{s['harness_precision'] * 100:.0f}%[/green], "
        f"provenance [green]{s['harness_provenance'] * 100:.0f}%[/green], "
        f"hallucinations caught [green]{s['hallucinations']}[/green]"
        + (f", bare-LLM coverage [red]{s['baseline_accuracy'] * 100:.0f}%[/red]"
           if s["baseline_accuracy"] is not None else "")
    )


if __name__ == "__main__":
    main()
