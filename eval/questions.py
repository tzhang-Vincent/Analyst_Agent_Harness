"""Evaluation question set.

Four categories of the kind of question a sector analyst actually asks:

- ``cross_quarter`` — one metric across recent quarters for one company.
- ``cross_company`` — the same metric across several companies.
- ``single_metric`` — a specific metric, often with provenance in mind.
- ``annual`` — fiscal-year (not quarterly) comparisons.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Question:
    id: str
    text: str
    tickers: list[str]
    metrics: list[str]
    frequency: str = "quarterly"
    n: int = 4
    category: str = "cross_quarter"


QUESTIONS: list[Question] = [
    Question("q01", "What was NVDA's revenue in each of the last 4 quarters?", ["NVDA"], ["revenue"]),
    Question("q02", "Compare AMD revenue and net income over the last 4 quarters.", ["AMD"], ["revenue", "net_income"]),
    Question("q03", "What was MSFT's R&D expense in each of the last 4 quarters?", ["MSFT"], ["rd_expense"]),
    Question("q04", "Show AAPL's gross profit over the last 4 quarters.", ["AAPL"], ["gross_profit"]),
    Question("q05", "Compare NVDA, AMD and INTC net income over the last 4 quarters.", ["NVDA", "AMD", "INTC"], ["net_income"], category="cross_company"),
    Question("q06", "What were NVDA's total assets in each of the last 4 quarters?", ["NVDA"], ["total_assets"], category="single_metric"),
    Question("q07", "What was INTC's operating cash flow in the last 4 quarters?", ["INTC"], ["operating_cash_flow"], category="single_metric"),
    Question("q08", "What was MSFT's diluted EPS in each of the last 4 quarters?", ["MSFT"], ["diluted_eps"], category="single_metric"),
    Question("q09", "What was NVDA's annual revenue for the last 2 fiscal years?", ["NVDA"], ["revenue"], frequency="annual", n=2, category="annual"),
    Question("q10", "What were AAPL's cash and equivalents in each of the last 4 quarters?", ["AAPL"], ["cash"], category="single_metric"),
    Question("q11", "Compare NVDA and AMD revenue over the last 4 quarters.", ["NVDA", "AMD"], ["revenue"], category="cross_company"),
    Question("q12", "What was NVDA's cost of revenue in the last 4 quarters?", ["NVDA"], ["cost_of_revenue"]),
    Question("q13", "What was INTC's operating income in the last 4 quarters?", ["INTC"], ["operating_income"]),
    Question("q14", "What was MSFT's annual net income for the last 2 fiscal years?", ["MSFT"], ["net_income"], frequency="annual", n=2, category="annual"),
    Question("q15", "What was AMD's R&D expense in the last 4 quarters?", ["AMD"], ["rd_expense"], category="single_metric"),
]
