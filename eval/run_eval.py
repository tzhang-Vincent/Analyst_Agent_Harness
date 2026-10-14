"""Run the evaluation.

Metrics:

- **harness value accuracy** — fraction of oracle (EDGAR) values the harness
  reproduces. Expected ~100%: the harness's numbers are deterministic.
- **harness provenance coverage** — fraction of its facts carrying a filing
  link. Expected 100%.
- **baseline value accuracy** — same fraction for a bare LLM answering from
  memory with no tools. This is the "ChatGPT" equivalent, and it should be far
  lower because the model has no way to pull real filings.

Run::

    python -m eval.run_eval                 # harness + provenance only
    python -m eval.run_eval --baseline      # also the bare-LLM baseline (needs a key)
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
from .report import EvalRow, provenance_coverage, summarize, value_coverage

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
    p.add_argument("--provider", choices=["anthropic", "openai", "deepseek"])
    p.add_argument("--model")
    args = p.parse_args(argv)

    llm: LLM | None = None
    if args.baseline and is_configured(args.provider):
        llm = LLM(args.provider, args.model)
    elif args.baseline:
        console.print("[yellow]--baseline requested but no LLM key configured; skipping.[/yellow]")

    rows: list[EvalRow] = []
    with EdgarClient() as client:
        analyst = Analyst(client=client, memory=Memory("data/eval_memory"))
        for q in QUESTIONS:
            oracle = build_oracle(client, q)
            oracle_values = [o.value for o in oracle]

            answer = analyst.run(q.text)
            harness_values = [f.provenance.value for f in answer.facts]
            hcov = value_coverage(harness_values, oracle_values)
            prov = provenance_coverage(answer.facts)

            bcov = None
            if llm is not None:
                bcov = value_coverage(_baseline_answer(llm, q.text), oracle_values)

            rows.append(EvalRow(q.id, q.category, len(oracle_values), hcov, prov, bcov))

    table = Table(title="Evaluation")
    table.add_column("Q", justify="right")
    table.add_column("Category")
    table.add_column("Oracle values", justify="right")
    table.add_column("Harness acc.", justify="right")
    table.add_column("Provenance", justify="right")
    if llm is not None:
        table.add_column("Baseline acc.", justify="right")
    for r in rows:
        row = [
            r.question_id, r.category, str(r.oracle_values),
            f"{r.harness_coverage * 100:.0f}%", f"{r.harness_provenance * 100:.0f}%",
        ]
        if llm is not None:
            row.append(f"{r.baseline_coverage * 100:.0f}%" if r.baseline_coverage is not None else "—")
        table.add_row(*row)
    console.print(table)

    s = summarize(rows)
    console.print(
        f"\n[b]Overall[/b]: {s['questions']} questions — "
        f"harness accuracy [green]{s['harness_accuracy'] * 100:.0f}%[/green], "
        f"provenance [green]{s['harness_provenance'] * 100:.0f}%[/green]"
        + (f", baseline accuracy [red]{s['baseline_accuracy'] * 100:.0f}%[/red]"
           if s["baseline_accuracy"] is not None else "")
    )


if __name__ == "__main__":
    main()
