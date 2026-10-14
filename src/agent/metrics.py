"""Canonical metric registry.

Maps analyst vocabulary ("revenue", "net income", ...) onto us-gaap XBRL
concepts, with an ordered list of synonym tags per metric. The extractor walks
the list in order and falls back to the next synonym when a company does not
file the primary tag, which is the single most common cause of "wrong number"
in naive financial agents.
"""

from __future__ import annotations

from typing import Any


class MetricSpec:
    __slots__ = ("key", "label", "statement", "tags", "unit_pref", "kind")

    def __init__(
        self,
        key: str,
        label: str,
        statement: str,
        tags: list[str],
        unit_pref: list[str] | None = None,
        kind: str = "duration",
    ) -> None:
        self.key = key
        self.label = label
        self.statement = statement
        self.tags = tags
        # Preferred SEC unit(s), in order. Monetary metrics default to USD.
        self.unit_pref = unit_pref or ["USD", "shares"]
        # "duration" = flow over a period (income/cash flow); "instant" =
        # point-in-time balance (balance sheet items have start == end == None).
        self.kind = kind


# key -> spec. Tag order matters: primary first, synonyms after.
METRICS: dict[str, MetricSpec] = {
    "revenue": MetricSpec(
        "revenue",
        "Revenue",
        "income",
        [
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "Revenues",
            "SalesRevenueNet",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
        ],
    ),
    "net_income": MetricSpec(
        "net_income",
        "Net Income",
        "income",
        ["NetIncomeLoss", "ProfitLoss"],
    ),
    "gross_profit": MetricSpec(
        "gross_profit",
        "Gross Profit",
        "income",
        ["GrossProfit"],
    ),
    "operating_income": MetricSpec(
        "operating_income",
        "Operating Income",
        "income",
        ["OperatingIncomeLoss"],
    ),
    "rd_expense": MetricSpec(
        "rd_expense",
        "R&D Expense",
        "income",
        ["ResearchAndDevelopmentExpense"],
    ),
    "cost_of_revenue": MetricSpec(
        "cost_of_revenue",
        "Cost of Revenue",
        "income",
        ["CostOfRevenue", "CostOfGoodsAndServicesSold"],
    ),
    "total_assets": MetricSpec(
        "total_assets",
        "Total Assets",
        "balance_sheet",
        ["Assets"],
        kind="instant",
    ),
    "total_liabilities": MetricSpec(
        "total_liabilities",
        "Total Liabilities",
        "balance_sheet",
        ["Liabilities"],
        kind="instant",
    ),
    "cash": MetricSpec(
        "cash",
        "Cash & Equivalents",
        "balance_sheet",
        ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
        kind="instant",
    ),
    "operating_cash_flow": MetricSpec(
        "operating_cash_flow",
        "Operating Cash Flow",
        "cash_flow",
        ["NetCashProvidedByUsedInOperatingActivities"],
    ),
    "diluted_eps": MetricSpec(
        "diluted_eps",
        "Diluted EPS",
        "income",
        ["EarningsPerShareDiluted"],
        unit_pref=["USD/shares", "USDPerShare", "shares"],
    ),
    "shares_outstanding": MetricSpec(
        "shares_outstanding",
        "Diluted Shares Outstanding",
        "income",
        ["WeightedAverageNumberOfDilutedSharesOutstanding"],
        unit_pref=["shares"],
    ),
}

# Natural-language aliases -> canonical key.
ALIASES: dict[str, str] = {
    "revenue": "revenue",
    "revenues": "revenue",
    "sales": "revenue",
    "top line": "revenue",
    "topline": "revenue",
    "net income": "net_income",
    "netincome": "net_income",
    "net profit": "net_income",
    "profit": "net_income",
    "earnings": "net_income",
    "gross profit": "gross_profit",
    "grossprofit": "gross_profit",
    "gross margin": "gross_profit",
    "operating income": "operating_income",
    "operatingincome": "operating_income",
    "op income": "operating_income",
    "operating profit": "operating_income",
    "r&d": "rd_expense",
    "r&d expense": "rd_expense",
    "rd": "rd_expense",
    "research and development": "rd_expense",
    "research & development": "rd_expense",
    "rd expense": "rd_expense",
    "cost of revenue": "cost_of_revenue",
    "costofrevenue": "cost_of_revenue",
    "cogs": "cost_of_revenue",
    "total assets": "total_assets",
    "assets": "total_assets",
    "total liabilities": "total_liabilities",
    "liabilities": "total_liabilities",
    "cash": "cash",
    "cash and equivalents": "cash",
    "cash & equivalents": "cash",
    "operating cash flow": "operating_cash_flow",
    "cash flow from operations": "operating_cash_flow",
    "ocf": "operating_cash_flow",
    "diluted eps": "diluted_eps",
    "eps": "diluted_eps",
    "earnings per share": "diluted_eps",
    "shares outstanding": "shares_outstanding",
    "diluted shares": "shares_outstanding",
    "share count": "shares_outstanding",
}


def canonical_metric(name: str) -> str | None:
    """Map free-text metric phrasing to a canonical key, or None."""
    key = name.strip().lower()
    if key in METRICS:
        return key
    return ALIASES.get(key)


def get_metric(key: str) -> MetricSpec | None:
    return METRICS.get(key)


def metric_tags(key: str) -> list[str]:
    spec = METRICS.get(key)
    return spec.tags if spec else []


def metric_label(key: str) -> str:
    spec = METRICS.get(key)
    return spec.label if spec else key


def metrics_for_statement(statement: str) -> list[str]:
    """Return canonical keys belonging to a statement type."""
    return [k for k, s in METRICS.items() if s.statement == statement]


def all_metrics() -> list[str]:
    return list(METRICS.keys())


def describe() -> dict[str, dict[str, Any]]:
    """Serializable registry (used to describe metrics to the LLM)."""
    return {
        k: {"label": v.label, "statement": v.statement, "tags": v.tags}
        for k, v in METRICS.items()
    }
