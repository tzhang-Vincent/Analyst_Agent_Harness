"""Deterministic extraction: turn raw EDGAR facts into typed :class:`Fact`.

XBRL ``frame`` labels are calendar-based and mislabel fiscal quarters for
companies whose fiscal year does not end in December, and ``companyfacts``
contains cumulative (YTD) facts and duplicated facts for the same period.
So instead of trusting ``frame`` (or the filing's ``fy`` year, which drifts
across restatements) we use the fact's actual dates:

- **Duration metrics** (income statement, cash flow) are flows over a period:
  filter by duration (~13 weeks = quarter, ~52 weeks = year) to drop YTD and
  point-in-time facts.
- **Instant metrics** (balance sheet) are point-in-time (``start`` is None):
  classify by the filing's ``fp`` (Q1-Q4 vs FY) instead.

Both paths dedupe by period keeping the *latest-filed* fact (restatements),
order by ``end`` date, and label from ``fp`` + an inferred fiscal year-end month.
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


def _dedupe_duration(
    facts_with_units: list[tuple[dict, str]], days_range: tuple[int, int]
) -> dict[tuple[str | None, str], dict]:
    """Collapse duration facts to one per (start, end), latest-filed wins."""
    best: dict[tuple[str | None, str], dict] = {}
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


def _dedupe_instant(
    facts_with_units: list[tuple[dict, str]], frequency: str
) -> dict[tuple[str | None, str], dict]:
    """Collapse instant (point-in-time) facts to one per end date, latest-filed wins."""
    best: dict[tuple[str | None, str], dict] = {}
    for fact, unit in facts_with_units:
        end = fact.get("end")
        if not end:
            continue
        fp = fact.get("fp")
        if frequency == "quarterly":
            # Q1-Q3 come from 10-Qs; the fiscal-year-end instant (fp == "FY")
            # *is* the Q4 balance sheet, so include it as well.
            if fp not in _FISCAL_QUARTERS and fp != "FY":
                continue
        elif fp != "FY":
            continue
        key = (fact.get("start"), end)
        filed = fact.get("filed") or ""
        if key not in best or filed > (best[key].get("filed") or ""):
            best[key] = {**fact, "_unit": unit}
    return best


def _infer_fy_end_month(tags_node: dict, spec: MetricSpec) -> int:
    """Infer the company's fiscal year-end month from any annual fact."""
    ends: list[str] = []
    for tag in list(spec.tags) + [t for t in tags_node if t not in spec.tags]:
        node = tags_node.get(tag)
        if not node:
            continue
        for facts in node.get("units", {}).values():
            for f in facts:
                end = f.get("end")
                if not end:
                    continue
                start = f.get("start")
                if f.get("fp") == "FY" or (
                    start and ANNUAL_DAYS[0] <= _days(start, end) <= ANNUAL_DAYS[1]
                ):
                    ends.append(end)
    return date.fromisoformat(max(ends)).month if ends else 12


def _fiscal_year(end: str, fy_end_month: int) -> int:
    """Fiscal year (ending-year convention) containing a period end date."""
    d = date.fromisoformat(end)
    return d.year + 1 if d.month > fy_end_month else d.year


def _period_label(
    fact: dict, end: str, fy_end_month: int, frame: str | None, frequency: str
) -> str:
    """Human label, e.g. 'Q2 FY2026' or 'FY2026', preferring fiscal quarter."""
    fp = fact.get("fp")
    fy = _fiscal_year(end, fy_end_month)
    if fp in _FISCAL_QUARTERS:
        return f"{fp} FY{fy}"
    if fp == "FY":
        return f"Q4 FY{fy}" if frequency == "quarterly" else f"FY{fy}"
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

    if spec.kind == "instant":
        filter_fn = lambda facts: _dedupe_instant(facts, frequency)
    else:
        days_range = QUARTER_DAYS if frequency == "quarterly" else ANNUAL_DAYS
        filter_fn = lambda facts: _dedupe_duration(facts, days_range)

    cik = client.ticker_to_cik(ticker)
    company_facts = client.get_company_facts(cik)
    entity_name = company_facts.get("entityName", "")
    tags_node = company_facts.get("facts", {}).get(_TAXONOMY, {})
    fy_end_month = _infer_fy_end_month(tags_node, spec)

    chosen_tag: str | None = None
    chosen_best: dict[tuple[str | None, str], dict] = {}
    chosen_latest_end = ""
    for tag in spec.tags:
        tag_node = tags_node.get(tag)
        if not tag_node:
            continue
        best = filter_fn(_facts_for_tag(tag_node, spec.unit_pref))
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
                period_label=_period_label(f, end, fy_end_month, frame, frequency),
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
