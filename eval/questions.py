"""Evaluation question set.

Four straightforward categories, plus a set of harder, adversarial ones:

- ``cross_quarter`` / ``cross_company`` / ``single_metric`` / ``annual`` — the
  kind of explicit question a sector analyst asks.
- ``implicit`` — the metric is implied, not named ("profitable" -> net_income).
- ``multi_hop`` — answering needs several companies/metrics and a derived ranking.
- ``trick`` — the data does not exist; the right answer is "no data", not a guess.
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
    # open_ended questions have no single "correct" (metric, frequency) spec —
    # e.g. "profitability" — so coverage/precision are N/A; only provenance and
    # hallucination are scored.
    open_ended: bool = False


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

    # Hard / adversarial — implicit metrics, multi-hop reasoning, and a no-data
    # trap. These stress the LLM's tool-call planning, not just extraction.
    Question("q16", "How profitable was NVDA in its latest quarter?", ["NVDA"], ["net_income"], n=1, category="implicit", open_ended=True),
    Question("q17", "Which of NVDA, AMD and INTC grew revenue fastest over the last year?", ["NVDA", "AMD", "INTC"], ["revenue"], category="multi_hop"),
    Question("q18", "Which of NVDA and AMD had the higher gross margin last quarter?", ["NVDA", "AMD"], ["revenue", "gross_profit"], n=1, category="multi_hop"),
    Question("q19", "What were AMD's total liabilities last quarter?", ["AMD"], ["total_liabilities"], n=1, category="trick"),
    Question("q20", "What is NVDA's cash position right now?", ["NVDA"], ["cash"], n=1, category="implicit"),
    Question("q21", "Compare the profitability of NVDA and AMD.", ["NVDA", "AMD"], ["net_income"], category="implicit", open_ended=True),
]
