"""Command-line interface (argparse + rich, no CLI-framework magic)."""

from __future__ import annotations

import argparse

from rich.console import Console

from .agent import Analyst
from .llm import LLM, is_configured
from .table import group_facts, render_terminal, to_csv, to_excel

console = Console()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agent",
        description="Financial research agent with full provenance tracking over SEC EDGAR.",
    )
    p.add_argument("query", help="Natural-language research question.")
    p.add_argument("-o", "--export", help="Write results to an .xlsx or .csv file.")
    p.add_argument("--provider", choices=["anthropic", "openai", "deepseek"],
                   help="LLM provider (default: $LLM_PROVIDER).")
    p.add_argument("--model", help="Model id (default: $LLM_MODEL).")
    p.add_argument("--memory-dir", default="data/memory", help="User memory directory.")
    p.add_argument("--no-llm", action="store_true",
                   help="Deterministic mode: no LLM, template summary only.")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    llm = None
    if not args.no_llm and is_configured(args.provider):
        llm = LLM(args.provider, args.model)

    analyst = Analyst(llm=llm, memory_dir=args.memory_dir)
    answer = analyst.run(args.query)

    console.print(answer.summary)
    if answer.facts:
        console.print()
        console.print(render_terminal(group_facts(answer.facts), title="Comparison"))

    if args.export:
        if args.export.endswith(".csv"):
            to_csv(answer.facts, args.export)
        else:
            to_excel(group_facts(answer.facts), args.export)
        console.print(f"\n[green]Exported to {args.export}[/green]")


if __name__ == "__main__":
    main()
