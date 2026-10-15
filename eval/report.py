"""Eval metrics and reporting."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EvalRow:
    question_id: str
    category: str
    oracle_values: int
    intent_ok: bool | None = None  # None = N/A (agent mode has no explicit intent)
    harness_coverage: float | None = 1.0  # None = N/A (open-ended question)
    harness_provenance: float = 1.0
    harness_precision: float | None = 1.0  # None = N/A (open-ended question)
    hallucinations: int = 0      # unsupported numbers the verifier caught & removed
    baseline_coverage: float | None = None


def value_coverage(claimed: list[float], oracle: list[float], tol: float = 0.01) -> float:
    """Recall: fraction of oracle values matched by a claimed number."""
    if not oracle:
        return 1.0
    hit = sum(
        1
        for ov in oracle
        if any(abs(cv - ov) <= abs(ov) * tol + 1 for cv in claimed)
    )
    return hit / len(oracle)


def value_precision(claimed: list[float], oracle: list[float], tol: float = 0.01) -> float:
    """Precision: fraction of claimed values that are backed by an oracle value.

    Catches the harness fetching the *wrong* companies/metrics (e.g. a ticker
    leak), which recall alone would not flag.
    """
    if not claimed:
        return 1.0
    hit = sum(
        1
        for cv in claimed
        if any(abs(cv - ov) <= abs(ov) * tol + 1 for ov in oracle)
    )
    return hit / len(claimed)


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
        return {
            "questions": 0,
            "intent_accuracy": 0.0,
            "harness_accuracy": 0.0,
            "harness_precision": 0.0,
            "harness_provenance": 0.0,
            "hallucinations": 0,
            "baseline_accuracy": None,
        }
    base = [r.baseline_coverage for r in rows if r.baseline_coverage is not None]
    intents = [r.intent_ok for r in rows if r.intent_ok is not None]
    covs = [r.harness_coverage for r in rows if r.harness_coverage is not None]
    precs = [r.harness_precision for r in rows if r.harness_precision is not None]
    return {
        "questions": n,
        "intent_accuracy": (sum(1 for i in intents if i) / len(intents)) if intents else None,
        "harness_accuracy": (sum(covs) / len(covs)) if covs else None,
        "harness_precision": (sum(precs) / len(precs)) if precs else None,
        "harness_provenance": sum(r.harness_provenance for r in rows) / n,
        "hallucinations": sum(r.hallucinations for r in rows),
        "baseline_accuracy": (sum(base) / len(base)) if base else None,
    }
