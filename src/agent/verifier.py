"""Final gate: no number ships unless it is backed by a fetched fact.

The LLM is only allowed to *arrange* fact values, never invent one. This module
extracts every numeric token from the generated summary and checks it against
the fact set; anything that does not match is flagged so it can be dropped.
"""

from __future__ import annotations

import re

from .schema import Answer, Fact

# Only *financial* numbers: a dollar amount, or a magnitude-suffixed amount
# (B/M/T/K). This avoids matching quarter numbers ("Q2"), fiscal years ("2025"),
# citation indices ("[1]") or percentages ("+22.0%"), none of which are values
# we are verifying against the facts.
_FIN_NUM_RE = re.compile(
    r"-?\$\d[\d,]*(?:\.\d+)?\s*[TBMK]?|-?\d[\d,]*(?:\.\d+)?\s*[TBMK]",
    re.IGNORECASE,
)

_MULT = {"T": 1e12, "B": 1e9, "M": 1e6, "K": 1e3}


def parse_number(token: str) -> float | None:
    s = token.replace("$", "").replace(",", "").strip()
    mult = 1.0
    if s and s[-1].upper() in _MULT:
        mult = _MULT[s[-1].upper()]
        s = s[:-1].strip()
    if not s:
        return None
    try:
        return float(s) * mult
    except ValueError:
        return None


def extract_numbers(text: str) -> list[float]:
    return [
        n
        for tok in _FIN_NUM_RE.findall(text)
        if (n := parse_number(tok)) is not None
    ]


def unsupported_numbers(
    text: str, facts: list[Fact], tolerance_frac: float = 0.01
) -> list[float]:
    """Financial numbers in ``text`` not backed by any fact value."""
    fact_values = {f.provenance.value for f in facts}
    return [
        num
        for num in extract_numbers(text)
        if not any(abs(num - v) <= abs(v) * tolerance_frac + 1 for v in fact_values)
    ]


def verify(answer: Answer, tolerance_frac: float = 0.01) -> list[str]:
    """Return a list of human-readable problems; empty means the answer is clean."""
    issues: list[str] = []

    for f in answer.facts:
        p = f.provenance
        if not p.accession_number or not p.source_url:
            issues.append(f"{f.metric} {f.period}: missing provenance (no filing link)")

    fact_values = {f.provenance.value for f in answer.facts}
    for num in extract_numbers(answer.summary):
        if not any(abs(num - v) <= abs(v) * tolerance_frac + 1 for v in fact_values):
            issues.append(f"summary number {num:,.0f} is not backed by any fetched fact")

    return issues


def sanitize_summary(
    summary: str, facts: list[Fact], tolerance_frac: float = 0.01
) -> str:
    """Replace numeric claims in prose that have no backing fact with ``[unverified]``.

    This actually *removes* hallucinated numbers from the text, rather than just
    flagging them, so nothing unsupported ships to the user.
    """
    fact_values = {f.provenance.value for f in facts}

    def _repl(match):
        tok = match.group(0)
        n = parse_number(tok)
        if n is None:
            return tok
        supported = any(abs(n - v) <= abs(v) * tolerance_frac + 1 for v in fact_values)
        return tok if supported else "[unverified]"

    return _FIN_NUM_RE.sub(_repl, summary)
