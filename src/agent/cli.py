"""Command-line interface (argparse + rich, no CLI-framework magic)."""

from __future__ import annotations

import argparse
import os

from rich.console import Console

from .analyst import Analyst
from .llm import LLM, is_configured
from .profile import Memory
from .table import group_facts, render_terminal, to_csv, to_excel

console = Console()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agent",
        description="Financial research agent with full provenance tracking over SEC EDGAR.",
    )
    p.add_argument("query", nargs="?", help="Natural-language research question.")
    p.add_argument("-o", "--export", help="Write results to an .xlsx or .csv file "
                   "(a bare filename goes into --output-dir).")
    p.add_argument("--output-dir", default="output",
                   help="Directory for -o exports (default: output/).")
    p.add_argument("--correct", help="Record a user correction/preference "
                   "(e.g. 'I want annual data, not quarterly'), then exit.")
    p.add_argument("--provider", choices=["anthropic", "openai", "deepseek"],
                   help="LLM provider (default: $LLM_PROVIDER).")
    p.add_argument("--model", help="Model id (default: $LLM_MODEL).")
    p.add_argument("--memory-dir", default="data/memory", help="User memory directory.")
    p.add_argument("--mode", choices=["pipeline", "agent"], default="agent",
                   help="agent = LLM drives tool calls (default); "
                        "pipeline = deterministic orchestration.")
    p.add_argument("--no-llm", action="store_true",
                   help="Deterministic mode: no LLM, template summary only.")
    p.add_argument("--chat", action="store_true",
                   help="Enter an interactive conversation (agent mode).")
    return p


def run_chat(args) -> None:
    """Interactive multi-turn conversation (agent mode, with in-session history)."""
    if not is_configured(args.provider):
        console.print("[red]Chat mode needs an LLM key (set LLM_PROVIDER/LLM_MODEL + a key).[/red]")
        return
    analyst = Analyst(llm=LLM(args.provider, args.model), memory_dir=args.memory_dir, mode="agent")
    history: list[dict] = []
    console.print("[bold]Interactive conversation (agent mode).[/bold] "
                  "Type 'exit' / 'quit' / 'q' to leave.")
    while True:
        try:
            query = input("agent> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not query:
            continue
        if query.lower() in ("exit", "quit", "q"):
            break
        answer = analyst.run(query, history=history)
        console.print()
        console.print(answer.summary, markup=False)
        if answer.citations:
            console.print("\n[bold]Sources[/bold] (clickable)")
            for i, url in enumerate(answer.citations, 1):
                console.print(f"  [{i}] [link={url}]{url}[/link]")
        history.append({"role": "user", "content": query})
        history.append({"role": "assistant", "content": answer.summary})
        console.print()


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    if args.correct:
        memory = Memory(args.memory_dir)
        memory.record_correction(args.correct)
        memory.save()
        console.print(f"[green]Recorded correction:[/green] {args.correct}")
        return

    if args.chat:
        run_chat(args)
        return

    if not args.query:
        build_parser().print_help()
        return

    llm = None
    if not args.no_llm and is_configured(args.provider):
        llm = LLM(args.provider, args.model)

    analyst = Analyst(llm=llm, memory_dir=args.memory_dir, mode=args.mode)
    answer = analyst.run(args.query)

    console.print(answer.summary, markup=False)

    # Render the provenance sources as clickable links (OSC 8) in the terminal.
    if answer.citations:
        console.print("\n[bold]Sources[/bold] (clickable)")
        for i, url in enumerate(answer.citations, 1):
            console.print(f"  [{i}] [link={url}]{url}[/link]")

    if answer.facts:
        console.print()
        console.print(render_terminal(group_facts(answer.facts), title="Comparison"))

    if args.export:
        path = args.export
        if not os.path.isabs(path):
            os.makedirs(args.output_dir, exist_ok=True)
            path = os.path.join(args.output_dir, path)
        if path.endswith(".csv"):
            to_csv(answer.facts, path)
        else:
            to_excel(group_facts(answer.facts), path)
        console.print(f"\n[green]Exported to {path}[/green]")


if __name__ == "__main__":
    main()
