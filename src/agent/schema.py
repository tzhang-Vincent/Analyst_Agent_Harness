"""Core data model: every numeric claim in the system carries a :class:`Provenance`.

The whole point of this harness is that a financial number is never emitted
without the exact filing it came from. ``Provenance`` is the single source of
truth that lets an analyst click through and double-check any cell against the
original SEC filing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Provenance(BaseModel):
    """Where a single number came from, traceable to one SEC filing."""

    ticker: str
    cik: str = Field(description="10-digit SEC Central Index Key")
    entity_name: str = ""
    xbrl_tag: str = Field(description="us-gaap concept, e.g. NetIncomeLoss")
    xbrl_label: str = ""
    unit: str = ""
    value: float
    start_date: str | None = None
    end_date: str | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = Field(
        default=None, description="FY, Q1, Q2, Q3 or Q4 (derived from the frame)"
    )
    form: str | None = Field(default=None, description="10-K, 10-Q, ...")
    accession_number: str | None = Field(
        default=None, description="e.g. 0001045810-19-000023"
    )
    filed_date: str | None = None
    source_url: str | None = Field(
        default=None, description="Link to the filing index page on sec.gov"
    )
    retrieved_at: str = Field(default_factory=_now)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump()


class Fact(BaseModel):
    """A single metric value for a single company and period, with provenance."""

    metric: str = Field(description="canonical metric key, e.g. revenue")
    period: str = Field(
        description="canonical period key = the period's end date (YYYY-MM-DD)"
    )
    period_label: str = Field(
        default="", description="human label, e.g. 'Q2 FY2026' or 'FY2026'"
    )
    provenance: Provenance


class QueryIntent(BaseModel):
    """Structured parse of a natural-language analyst question."""

    tickers: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    num_periods: int = 4
    frequency: str = "quarterly"  # quarterly | annual
    statement_type: str | None = None  # income | balance_sheet | cash_flow
    raw_query: str = ""


class Answer(BaseModel):
    """The agent's response: prose summary + the facts it is built from."""

    summary: str = ""
    facts: list[Fact] = Field(default_factory=list)
    citations: list[str] = Field(
        default_factory=list,
        description="source_urls referenced in the summary, in citation order",
    )

    def provenance_coverage(self) -> tuple[int, int]:
        """Return (facts_with_provenance, total_facts)."""
        total = len(self.facts)
        covered = sum(
            1
            for f in self.facts
            if f.provenance.accession_number and f.provenance.source_url
        )
        return covered, total
