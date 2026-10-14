"""Deterministic tools the agent composes.

These are the *data primitives*: the LLM decides which to call (or a skill
prescribes the sequence), but the execution is deterministic EDGAR extraction.
Every returned fact carries provenance, so nothing here can hallucinate.
"""

from __future__ import annotations

from .edgar import EdgarClient
from .extractor import extract_metric, extract_metrics
from .metrics import MetricSpec, get_metric, metric_label, metrics_for_statement
from .schema import Fact

INCOME_STATEMENT_METRICS = [
    "revenue",
    "cost_of_revenue",
    "gross_profit",
    "rd_expense",
    "operating_income",
    "net_income",
    "diluted_eps",
]
BALANCE_SHEET_METRICS = ["total_assets", "total_liabilities", "cash"]
CASH_FLOW_METRICS = ["operating_cash_flow"]


def get_income_statement(
    client: EdgarClient,
    ticker: str,
    metric_keys: list[str] | None = None,
    frequency: str = "quarterly",
    n: int = 4,
) -> dict[str, list[Fact]]:
    keys = metric_keys or INCOME_STATEMENT_METRICS
    return extract_metrics(client, ticker, keys, frequency=frequency, n=n)


def get_balance_sheet(
    client: EdgarClient,
    ticker: str,
    metric_keys: list[str] | None = None,
    frequency: str = "quarterly",
    n: int = 4,
) -> dict[str, list[Fact]]:
    keys = metric_keys or BALANCE_SHEET_METRICS
    return extract_metrics(client, ticker, keys, frequency=frequency, n=n)


def get_cash_flow(
    client: EdgarClient,
    ticker: str,
    metric_keys: list[str] | None = None,
    frequency: str = "quarterly",
    n: int = 4,
) -> dict[str, list[Fact]]:
    keys = metric_keys or CASH_FLOW_METRICS
    return extract_metrics(client, ticker, keys, frequency=frequency, n=n)


def get_concept(
    client: EdgarClient,
    ticker: str,
    metric_key: str,
    frequency: str = "quarterly",
    n: int = 4,
) -> list[Fact]:
    return extract_metric(client, ticker, metric_key, frequency=frequency, n=n)


def compare_companies(
    client: EdgarClient,
    tickers: list[str],
    metric_keys: list[str],
    frequency: str = "quarterly",
    n: int = 4,
) -> dict[str, dict[str, list[Fact]]]:
    """Fetch the same metrics for several companies."""
    return {
        t: extract_metrics(client, t, metric_keys, frequency=frequency, n=n)
        for t in tickers
    }


def metric_spec(metric_key: str) -> MetricSpec | None:
    return get_metric(metric_key)


def describe_metrics(metric_keys: list[str]) -> str:
    """One-line descriptions of metrics for the LLM summary prompt."""
    return ", ".join(f"{k} ({metric_label(k)})" for k in metric_keys)


def metrics_of_statement(statement: str) -> list[str]:
    return metrics_for_statement(statement)
