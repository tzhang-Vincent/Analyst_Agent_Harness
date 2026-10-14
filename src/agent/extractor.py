"""Deterministic extraction: turn raw EDGAR facts into typed :class:`Fact`.

XBRL ``frame`` labels are calendar-based and mislabel fiscal quarters for
companies whose fiscal year does not end in December, and ``companyfacts``
contains cumulative (YTD) facts and duplicated facts for the same period.
So instead of trusting ``frame`` (or the filing's ``fy`` year, which drifts
across restatements) we use the fact's actual duration and dates:

1. **Duration filter** — a quarter is ~13 weeks, a fiscal year ~52 weeks.
   This drops cumulative YTD facts (6mo/9mo) and point-in-time balances.
2. **Dedupe by (start, end)** keeping the *latest-filed* fact, which absorbs
   restatements made in a later 10-K and duplicate filings for one period.
3. **Order by ``end`` date** — the one unambiguous chronological anchor.
4. **Label** — quarter number from ``fp``, fiscal *year* inferred from the end
   date and the company's fiscal year-end month (inferred from annual facts).
"""

from __future__ import annotations

from datetime import date

from .edgar import EdgarClient, filing_index_url
from .metrics import MetricSpec, get_metric
from .schema import Fact, Provenance

# A quarter is ~13 weeks (91 days); a fiscal year ~52 weeks (364 days).
QUARTER_DAYS = (60, 140)
ANNUAL_DAYS = (350, 380)

_FISCAL_QUARTERS = {"Q1", "Q2", "Q3", "Q4"}

_TAXONOMY = "us-gaap"


def _days(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def _facts_for_tag(tag_node: dict, unit_pref: list[str]) -> list[tuple[dict, str]]:
    """Return ``(fact_dict, unit)`` pairs for a tag, preferring ``unit_pref`` units."""
    units = tag_node.get("units", {})
    for unit in unit_pref:
        if units.get(unit):
            return [(f, unit) for f in units[unit]]
    for unit, facts in units.items():
        if facts:
            return [(f, unit) for f in facts]
    return []


def _dedupe(
    facts_with_units: list[tuple[dict, str]], days_range: tuple[int, int]
) -> dict[tuple[str, str], dict]:
    """Collapse to one fact per (start, end) period, keeping the latest-filed."""
    best: dict[tuple[str, str], dict] = {}
    for fact, unit in facts_with_units:
        start, end = fact.get("start"), fact.get("end")
        if not start or not end:
            continue
        if not (days_range[0] <= _days(start, end) <= days_range[1]):
            continue
        key = (start, end)
        filed = fact.get("filed") or ""
        if key not in best or filed > (best[key].get("filed") or ""):
            best[key] = {**fact, "_unit": unit}
    return best


def _infer_fy_end_month(tags_node: dict, spec: MetricSpec) -> int:
    """Infer the company's fiscal year-end month from its annual facts.

    Falls back to December (calendar) when no annual facts are present.
    """
    for tag in spec.tags:
        annual = _dedupe(
            _facts_for_tag(tags_node.get(tag, {}), spec.unit_pref), ANNUAL_DAYS
        )
        if annual:
            return date.fromisoformat(max(k[1] for k in annual)).month
    for node in tags_node.values():
        annual = _dedupe(_facts_for_tag(node, spec.unit_pref), ANNUAL_DAYS)
        if annual:
            return date.fromisoformat(max(k[1] for k in annual)).month
    return 12


def _fiscal_year(end: str, fy_end_month: int) -> int:
    """Fiscal year (ending-year convention) containing a period end date."""
    d = date.fromisoformat(end)
    return d.year + 1 if d.month > fy_end_month else d.year


def _period_label(fact: dict, end: str, fy_end_month: int, frame: str | None) -> str:
    """Human label, e.g. 'Q2 FY2026' or 'FY2026', preferring fiscal quarter."""
    fp = fact.get("fp")
    fy = _fiscal_year(end, fy_end_month)
    if fp in _FISCAL_QUARTERS:
        return f"{fp} FY{fy}"
    if fp == "FY":
        return f"FY{fy}"
    if frame:
        return frame
    return f"ended {end}"


def extract_metric(
    client: EdgarClient,
    ticker: str,
    metric_key: str,
    frequency: str = "quarterly",
    n: int = 4,
    periods: list[str] | None = None,
) -> list[Fact]:
    """Extract up to ``n`` latest periods for one metric of one company.

    Args:
        frequency: ``quarterly`` or ``annual``.
        periods: optional list of ``end`` dates to return (overrides ``n``).
    """
    spec: MetricSpec | None = get_metric(metric_key)
    if spec is None:
        raise ValueError(f"Unknown metric key: {metric_key}")

    days_range = QUARTER_DAYS if frequency == "quarterly" else ANNUAL_DAYS
    cik = client.ticker_to_cik(ticker)
    company_facts = client.get_company_facts(cik)
    entity_name = company_facts.get("entityName", "")
    tags_node = company_facts.get("facts", {}).get(_TAXONOMY, {})
    fy_end_month = _infer_fy_end_month(tags_node, spec)

    chosen_tag: str | None = None
    chosen_best: dict[tuple[str, str], dict] = {}
    chosen_latest_end = ""
    for tag in spec.tags:
        tag_node = tags_node.get(tag)
        if not tag_node:
            continue
        best = _dedupe(_facts_for_tag(tag_node, spec.unit_pref), days_range)
        if not best:
            continue
        # Prefer the tag the company is *currently* filing: the one whose most
        # recent period ends latest. Ties keep the earlier-listed (primary) tag.
        latest_end = max(k[1] for k in best)
        if latest_end > chosen_latest_end:
            chosen_tag, chosen_best, chosen_latest_end = tag, best, latest_end

    if chosen_tag is None:
        return []

    label = tags_node[chosen_tag].get("label", spec.label)
    keys = sorted(chosen_best.keys(), key=lambda k: k[1])

    if periods is not None:
        keys = [
            k for k in keys
            if k[1] in periods or chosen_best[k].get("frame") in periods
        ]
    else:
        keys = keys[-n:]

    result: list[Fact] = []
    for start, end in keys:
        f = chosen_best[start, end]
        accn = f.get("accn")
        frame = f.get("frame") if isinstance(f.get("frame"), str) else None
        fp = f.get("fp")
        prov = Provenance(
            ticker=ticker.upper(),
            cik=cik,
            entity_name=entity_name,
            xbrl_tag=chosen_tag,
            xbrl_label=label,
            unit=f.get("_unit", ""),
            value=float(f["val"]),
            start_date=start,
            end_date=end,
            fiscal_year=_fiscal_year(end, fy_end_month),
            fiscal_period=fp if fp in _FISCAL_QUARTERS else ("FY" if fp == "FY" else None),
            form=f.get("form"),
            accession_number=accn,
            filed_date=f.get("filed"),
            source_url=filing_index_url(cik, accn) if accn else None,
        )
        result.append(
            Fact(
                metric=metric_key,
                period=end,
                period_label=_period_label(f, end, fy_end_month, frame),
                provenance=prov,
            )
        )
    return result


def extract_metrics(
    client: EdgarClient,
    ticker: str,
    metric_keys: list[str],
    frequency: str = "quarterly",
    n: int = 4,
) -> dict[str, list[Fact]]:
    """Extract several metrics for one company in a single pass."""
    return {
        key: extract_metric(client, ticker, key, frequency=frequency, n=n)
        for key in metric_keys
    }
