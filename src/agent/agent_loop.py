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

from .edgar import EdgarClient
from .extractor import extract_metrics
from .metrics import canonical_metric, metric_label
from .schema import Fact

MAX_ITERATIONS = 6

AGENT_SYSTEM = (
    "You are a financial research analyst with access to SEC EDGAR data through "
    "tools. To answer any question about financial figures you MUST call the tools "
    "to fetch the real data first — never answer from memory or estimate a number. "
    "Then write a concise summary citing the fetched values with their source URLs. "
    "If a tool returns no data, say so instead of guessing."
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


def _facts_to_text(facts_by_company: dict[str, dict[str, list[Fact]]]) -> str:
    lines: list[str] = []
    for ticker in sorted(facts_by_company):
        for mk in sorted(facts_by_company[ticker]):
            for f in facts_by_company[ticker][mk]:
                p = f.provenance
                lines.append(
                    f"{ticker} {metric_label(mk)} {f.period_label}: "
                    f"{p.value:,.0f} {p.unit} | {p.source_url}"
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
    return {"text": _facts_to_text(facts_by_company), "facts": _flatten(facts_by_company)}


def run_agent_loop(llm, client: EdgarClient, query: str) -> tuple[str, list[Fact]]:
    """Run the tool-calling loop; return ``(final_text, facts)``."""
    import anthropic

    aclient = anthropic.Anthropic(base_url=llm.base_url or None)
    messages: list[dict] = [{"role": "user", "content": query}]
    all_facts: list[Fact] = []
    final_text = ""

    for _ in range(MAX_ITERATIONS):
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
        if not tool_uses:
            final_text = text
            break

        messages.append({"role": "assistant", "content": resp.content})
        tool_results = []
        for tu in tool_uses:
            result = execute_tool(tu.name, dict(tu.input or {}), client)
            all_facts.extend(result["facts"])
            tool_results.append(
                {"type": "tool_result", "tool_use_id": tu.id, "content": result["text"]}
            )
        messages.append({"role": "user", "content": tool_results})

    return final_text, all_facts
