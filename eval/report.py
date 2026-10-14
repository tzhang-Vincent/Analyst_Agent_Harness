"""Eval metrics and reporting."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EvalRow:
    question_id: str
    category: str
    oracle_values: int
    harness_coverage: float
    harness_provenance: float
    baseline_coverage: float | None = None


def value_coverage(claimed: list[float], oracle: list[float], tol: float = 0.01) -> float:
    """Fraction of oracle values matched by a claimed number within tolerance."""
    if not oracle:
        return 1.0
    hit = 0
    for ov in oracle:
        if any(abs(cv - ov) <= abs(ov) * tol + 1 for cv in claimed):
            hit += 1
    return hit / len(oracle)


def provenance_coverage(facts) -> float:
    """Fraction of facts with a resolvable filing link."""
    if not facts:
        return 1.0
    covered = sum(
        1 for f in facts if f.provenance.accession_number and f.provenance.source_url
    )
    return covered / len(facts)


def summarize(rows: list[EvalRow]) -> dict:
    n = len(rows)
    if n == 0:
        return {"questions": 0, "harness_accuracy": 0.0, "harness_provenance": 0.0, "baseline_accuracy": None}
    base = [r.baseline_coverage for r in rows if r.baseline_coverage is not None]
    return {
        "questions": n,
        "harness_accuracy": sum(r.harness_coverage for r in rows) / n,
        "harness_provenance": sum(r.harness_provenance for r in rows) / n,
        "baseline_accuracy": (sum(base) / len(base)) if base else None,
    }
