"""Agentic mode: the LLM drives data retrieval through tool calls.

Unlike the default pipeline (the harness decides what to fetch), here the LLM is
given tool definitions and *decides* which tools to call, in which order, then
writes the summary. The tools themselves are still deterministic EDGAR
extraction, so the numbers remain provenance-safe; the loop is capped and the
final answer still passes through the verifier.

The tool round-trip (``tool_use`` / ``tool_result``) is Anthropic-specific, so
this loop talks the Anthropic Messages API directly (the default provider).
"""

from __future__ import annotations

import json
import os

from .edgar import EdgarClient
from .extractor import extract_metrics
from .metrics import canonical_metric, metric_label
from .schema import Fact
from .verifier import summary_issues

MAX_ITERATIONS = 6

AGENT_SYSTEM = (
    "You are a financial research analyst with access to SEC EDGAR data through "
    "tools. To answer any question about financial figures you MUST call the tools "
    "to fetch the real data first — never answer from memory or estimate a number. "
    "Then write a concise summary citing each number with its [n] reference "
    "(e.g. 'revenue was $46.7B [1]'). Do NOT paste source URLs in your answer — "
    "use the [n] reference instead. If a tool returns no data, say so instead of guessing. "
    "Always output only the answer itself — never meta-commentary, acknowledgments, "
    "or explanations of what you changed or corrected."
)

TOOL_SCHEMAS = [
    {
        "name": "get_metrics",
        "description": (
            "Fetch financial metrics for one company over recent periods. "
            "Returns each value with its SEC filing provenance."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Uppercase ticker, e.g. NVDA"},
                "metrics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Canonical keys: revenue, net_income, gross_profit, "
                        "operating_income, rd_expense, cost_of_revenue, total_assets, "
                        "total_liabilities, cash, operating_cash_flow, diluted_eps, "
                        "shares_outstanding"
                    ),
                },
                "frequency": {"type": "string", "enum": ["quarterly", "annual"]},
                "n": {"type": "integer", "description": "number of periods (default 4)"},
            },
            "required": ["ticker", "metrics"],
        },
    },
    {
        "name": "compare_companies",
        "description": "Fetch the same metrics for several companies over recent periods.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers": {"type": "array", "items": {"type": "string"}},
                "metrics": {"type": "array", "items": {"type": "string"}},
                "frequency": {"type": "string", "enum": ["quarterly", "annual"]},
                "n": {"type": "integer"},
            },
            "required": ["tickers", "metrics"],
        },
    },
]


def _register(citations: list[str], url: str | None) -> int:
    if url and url not in citations:
        citations.append(url)
    return citations.index(url) + 1 if url in citations else 0


def _facts_to_text(facts_by_company: dict[str, dict[str, list[Fact]]], citations: list[str]) -> str:
    """Render fetched facts for the LLM, each source as a ``[n]`` reference."""
    lines: list[str] = []
    for ticker in sorted(facts_by_company):
        for mk in sorted(facts_by_company[ticker]):
            for f in facts_by_company[ticker][mk]:
                p = f.provenance
                n = _register(citations, p.source_url)
                lines.append(
                    f"{ticker} {metric_label(mk)} {f.period_label}: "
                    f"{p.value:,.0f} {p.unit} [{n}]"
                )
    return "\n".join(lines) if lines else "(no data found)"


def _flatten(facts_by_company: dict[str, dict[str, list[Fact]]]) -> list[Fact]:
    out: list[Fact] = []
    for ticker in sorted(facts_by_company):
        for mk in sorted(facts_by_company[ticker]):
            out.extend(facts_by_company[ticker][mk])
    return out


def execute_tool(name: str, args: dict, client: EdgarClient) -> dict:
    """Run a tool call and return ``{"text": <for the LLM>, "facts": <flat facts>}``.

    Args are validated: tickers against the SEC map, metrics against the registry,
    so an LLM-supplied bad argument cannot fetch the wrong thing.
    """
    tickers = args.get("tickers") or [args.get("ticker")]
    metrics = args.get("metrics") or []
    frequency = args.get("frequency") or "quarterly"
    n = args.get("n") or 4

    validated_tickers: list[str] = []
    for t in tickers:
        t = str(t).upper()
        try:
            client.ticker_to_cik(t)
            validated_tickers.append(t)
        except (KeyError, Exception):
            continue

    validated_metrics: list[str] = []
    for m in metrics:
        key = canonical_metric(str(m))
        if key and key not in validated_metrics:
            validated_metrics.append(key)

    facts_by_company = {
        t: extract_metrics(client, t, validated_metrics, frequency, n)
        for t in validated_tickers
    }
    return {"facts": _flatten(facts_by_company), "facts_by_company": facts_by_company}


def run_agent_loop(llm, client: EdgarClient, query: str) -> tuple[str, list[Fact], list[str]]:
    """Run the tool-calling loop; return ``(final_text, facts, citations)``."""
    import anthropic

    aclient = anthropic.Anthropic(
        base_url=llm.base_url or None,
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
    )
    messages: list[dict] = [{"role": "user", "content": query}]
    all_facts: list[Fact] = []
    citations: list[str] = []
    final_text = ""

    for iteration in range(MAX_ITERATIONS):
        kwargs = {
            "model": llm.model,
            "max_tokens": 4096,
            "messages": messages,
            "system": AGENT_SYSTEM,
            "tools": TOOL_SCHEMAS,
        }
        if llm.thinking:
            kwargs["thinking"] = {"type": llm.thinking}
        resp = aclient.messages.create(**kwargs)

        tool_uses = [b for b in resp.content if getattr(b, "type", "") == "tool_use"]
        text = "".join(
            getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text"
        )
        if tool_uses:
            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for tu in tool_uses:
                result = execute_tool(tu.name, dict(tu.input or {}), client)
                all_facts.extend(result["facts"])
                content = _facts_to_text(result["facts_by_company"], citations)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": tu.id, "content": content}
                )
            messages.append({"role": "user", "content": tool_results})
            continue

        # Draft answer with no tool calls: run the verifier as a mandatory
        # feedback step. Fabricated *and* misattributed numbers are fed back for
        # revision (the LLM cannot skip this); the final hard gate still sanitizes.
        issues = summary_issues(text, all_facts)
        if not issues or iteration >= MAX_ITERATIONS - 1:
            final_text = text
            break

        feedback = (
            "Rewrite your answer so every number is a fetched fact attributed to "
            "the right company/metric. Violations to fix:\n"
            + "\n".join(f"- {i}" for i in issues)
            + "\nOutput ONLY the rewritten answer."
        )
        messages.append({"role": "assistant", "content": resp.content})
        messages.append({"role": "user", "content": feedback})

    return final_text, all_facts, citations
