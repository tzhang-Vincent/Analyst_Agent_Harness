"""Comparison tables and spreadsheet export.

Every cell in the exported spreadsheet links back to the SEC filing it came
from, and a separate "Provenance" sheet lists each fact with its XBRL tag,
accession number and source URL so an analyst can double-check cell by cell.
"""

from __future__ import annotations

from typing import Iterable

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from .metrics import metric_label
from .schema import Fact

_LINK_FONT = Font(color="0563C1", underline="single")


def fmt(value: float) -> str:
    return f"{value:,.0f}"


def fmt_compact(value: float) -> str:
    """Compact human form: 46,743,000,000 -> $46.7B."""
    magnitude = abs(value)
    if magnitude >= 1e12:
        return f"${value / 1e12:.2f}T"
    if magnitude >= 1e9:
        return f"${value / 1e9:.2f}B"
    if magnitude >= 1e6:
        return f"${value / 1e6:.1f}M"
    return f"${value:,.0f}"


def collect_periods(facts_by_company: dict[str, dict[str, list[Fact]]]) -> list[str]:
    """All distinct period keys (end dates) across every company, sorted."""
    periods: set[str] = set()
    for metrics in facts_by_company.values():
        for facts in metrics.values():
            periods.update(f.period for f in facts)
    return sorted(periods)


def period_labels_map(
    facts_by_company: dict[str, dict[str, list[Fact]]], periods: Iterable[str]
) -> dict[str, str]:
    """Map each period key to a human label (first seen wins)."""
    labels: dict[str, str] = {}
    for metrics in facts_by_company.values():
        for facts in metrics.values():
            for f in facts:
                if f.period not in labels and f.period_label:
                    labels[f.period] = f.period_label
    return {p: labels.get(p, p) for p in periods}


def build_rows(
    facts_by_company: dict[str, dict[str, list[Fact]]],
    periods: list[str],
) -> list[dict]:
    """Flatten to rows of (ticker, metric) with a ``cells`` dict keyed by period."""
    rows: list[dict] = []
    for ticker in sorted(facts_by_company):
        for mk, facts in facts_by_company[ticker].items():
            row = {"ticker": ticker, "metric": mk, "cells": {}}
            for f in facts:
                row["cells"][f.period] = f
            rows.append(row)
    return rows


def render_terminal(
    facts_by_company: dict[str, dict[str, list[Fact]]],
    title: str = "Comparison",
) -> "Table":
    from rich.table import Table

    periods = collect_periods(facts_by_company)
    labels = period_labels_map(facts_by_company, periods)
    rows = build_rows(facts_by_company, periods)

    table = Table(title=title)
    table.add_column("Company")
    table.add_column("Metric")
    for p in periods:
        table.add_column(labels[p], justify="right")
    for row in rows:
        vals = [row["ticker"], metric_label(row["metric"])]
        for p in periods:
            f = row["cells"].get(p)
            vals.append(fmt_compact(f.provenance.value) if f else "—")
        table.add_row(*vals)
    return table


def to_excel(
    facts_by_company: dict[str, dict[str, list[Fact]]],
    path: str,
    title: str = "Comparison",
) -> None:
    """Write an .xlsx with a comparison sheet (hyperlink cells) + provenance sheet."""
    periods = collect_periods(facts_by_company)
    labels = period_labels_map(facts_by_company, periods)
    rows = build_rows(facts_by_company, periods)

    wb = Workbook()

    # Sheet 1: comparison grid with per-cell hyperlinks to the filing.
    ws = wb.active
    ws.title = "Comparison"
    header = ["Company", "Metric"] + [labels[p] for p in periods]
    ws.append(header)
    for row in rows:
        line = [row["ticker"], metric_label(row["metric"])]
        for p in periods:
            f = row["cells"].get(p)
            line.append(f.provenance.value if f else None)
        ws.append(line)
        r = ws.max_row
        for col_idx, p in enumerate(periods, start=3):
            f = row["cells"].get(p)
            if f and f.provenance.source_url:
                cell = ws.cell(row=r, column=col_idx)
                cell.hyperlink = f.provenance.source_url
                cell.font = _LINK_FONT

    # Sheet 2: flat provenance, one row per fact.
    pv = wb.create_sheet("Provenance")
    pv.append(
        [
            "ticker", "entity", "metric", "period_label", "period_end",
            "value", "unit", "xbrl_tag", "xbrl_label",
            "start_date", "end_date", "fiscal_year", "fiscal_period",
            "form", "accession_number", "filed_date", "source_url",
        ]
    )
    for metrics in facts_by_company.values():
        for facts in metrics.values():
            for f in facts:
                p = f.provenance
                pv.append(
                    [
                        p.ticker, p.entity_name, f.metric, f.period_label, f.period,
                        p.value, p.unit, p.xbrl_tag, p.xbrl_label,
                        p.start_date, p.end_date, p.fiscal_year, p.fiscal_period,
                        p.form, p.accession_number, p.filed_date, p.source_url,
                    ]
                )
                if p.source_url:
                    url_cell = pv.cell(row=pv.max_row, column=17)
                    url_cell.hyperlink = p.source_url
                    url_cell.font = _LINK_FONT

    # Reasonable column widths for the provenance sheet.
    for idx, width in enumerate([8, 28, 16, 14, 12, 16, 8, 40, 30, 12, 12, 12, 12, 8, 22, 12, 64], start=1):
        pv.column_dimensions[get_column_letter(idx)].width = width

    wb.save(path)


def to_csv(facts: list[Fact], path: str) -> None:
    """Flat CSV of facts with provenance columns."""
    import csv

    header = [
        "ticker", "entity", "metric", "period_label", "period_end",
        "value", "unit", "xbrl_tag", "start_date", "end_date",
        "fiscal_year", "fiscal_period", "form", "accession_number",
        "filed_date", "source_url",
    ]
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for f in facts:
            p = f.provenance
            writer.writerow(
                [
                    p.ticker, p.entity_name, f.metric, f.period_label, f.period,
                    p.value, p.unit, p.xbrl_tag, p.start_date, p.end_date,
                    p.fiscal_year, p.fiscal_period, p.form, p.accession_number,
                    p.filed_date, p.source_url,
                ]
            )


def flatten(facts_by_company: dict[str, dict[str, list[Fact]]]) -> list[Fact]:
    """All facts across companies, in a stable order."""
    out: list[Fact] = []
    for ticker in sorted(facts_by_company):
        for mk in sorted(facts_by_company[ticker]):
            out.extend(facts_by_company[ticker][mk])
    return out


def group_facts(facts: list[Fact]) -> dict[str, dict[str, list[Fact]]]:
    """Inverse of :func:`flatten`: rebuild ``{ticker: {metric: [facts]}}``."""
    out: dict[str, dict[str, list[Fact]]] = {}
    for f in facts:
        out.setdefault(f.provenance.ticker, {}).setdefault(f.metric, []).append(f)
    return out
