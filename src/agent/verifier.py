"""Final gate: no number ships unless it is backed by a fetched fact.

Two kinds of checks, both against the deterministic facts:

1. **Fabrication** — a number not close to *any* fact value (a hallucinated or
   derived figure).
2. **Attribution** — a number that exists in the facts but is attached to the
   wrong company/metric in the prose (e.g. "AMD revenue $96B" when $96B is
   NVDA's). This splits the text into claims, detects the tickers/metrics each
   claim names, and requires the number to match a fact for *those* entities.
"""

from __future__ import annotations

import re

from .metrics import ALIASES, metric_label
from .schema import Answer, Fact

# Only *financial* numbers: a dollar amount, or a magnitude-suffixed amount
# (B/M/T/K). This avoids matching quarter numbers ("Q2"), fiscal years ("2025"),
# citation indices ("[1]") or percentages ("+22.0%"), none of which are values.
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


def _matches(num: float, values, tolerance_frac: float = 0.01) -> bool:
    return any(abs(num - v) <= abs(v) * tolerance_frac + 1 for v in values)


def unsupported_numbers(
    text: str, facts: list[Fact], tolerance_frac: float = 0.01
) -> list[float]:
    """Financial numbers in ``text`` not backed by *any* fact value (fabrication)."""
    fact_values = {f.provenance.value for f in facts}
    return [num for num in extract_numbers(text) if not _matches(num, fact_values, tolerance_frac)]


# --- attribution ----------------------------------------------------------

_metric_phrase_cache: dict[str, list[str]] = {}


def _metric_phrases(key: str) -> list[str]:
    """Human phrases that name a metric: its label plus all its aliases."""
    if key not in _metric_phrase_cache:
        phrases = [metric_label(key).lower()]
        for alias, k in ALIASES.items():
            if k == key:
                phrases.append(alias)
        _metric_phrase_cache[key] = phrases
    return _metric_phrase_cache[key]


def _detect_tickers(text: str, tickers: list[str]) -> list[str]:
    return [
        t for t in tickers if re.search(r"\b" + re.escape(t) + r"\b", text, re.IGNORECASE)
    ]


def _detect_metrics(text: str, metric_keys: list[str]) -> list[str]:
    t = text.lower()
    return [m for m in metric_keys if any(p in t for p in _metric_phrases(m))]


def _split_claims(text: str) -> list[str]:
    """Split into claim-sized chunks: one per line.

    A markdown-table row keeps its ticker/metric/value in the same line, so a
    line is the natural unit for attribution.
    """
    claims: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("---", "|--", "#", "Sources", "[")):
            continue
        claims.append(line)
    return claims


def _build_index(facts: list[Fact]):
    tickers = sorted({f.provenance.ticker for f in facts})
    metrics = sorted({f.metric for f in facts})
    by_entity: dict[tuple[str, str], set[float]] = {}
    all_values: set[float] = set()
    for f in facts:
        by_entity.setdefault((f.provenance.ticker, f.metric), set()).add(f.provenance.value)
        all_values.add(f.provenance.value)
    return tickers, metrics, by_entity, all_values


def _eligible_values(by_entity, all_values, ct, cm) -> set[float]:
    """Values a claim's numbers may legitimately cite, given the entities it names."""
    if not ct and not cm:
        return all_values
    eligible: set[float] = set()
    if ct and cm:
        for t in ct:
            for m in cm:
                eligible |= by_entity.get((t, m), set())
    elif ct:
        for (tt, mm), vals in by_entity.items():
            if tt in ct:
                eligible |= vals
    else:  # cm only
        for (tt, mm), vals in by_entity.items():
            if mm in cm:
                eligible |= vals
    return eligible


def attribution_issues(text: str, facts: list[Fact], tolerance_frac: float = 0.01) -> list[str]:
    """Numbers attached to the wrong company/metric in the prose."""
    tickers, metrics, by_entity, all_values = _build_index(facts)
    issues: list[str] = []
    for claim in _split_claims(text):
        numbers = extract_numbers(claim)
        if not numbers:
            continue
        ct = _detect_tickers(claim, tickers)
        cm = _detect_metrics(claim, metrics)
        if not ct and not cm:
            continue  # no attribution context; the fabrication check covers it
        eligible = _eligible_values(by_entity, all_values, ct, cm)
        for num in numbers:
            if not _matches(num, eligible, tolerance_frac):
                issues.append(
                    f"claim \"{claim[:60]}\" attributes {num:,.0f} to "
                    f"{ct or '-'}/{cm or '-'} but no matching fetched fact"
                )
    return issues


def summary_issues(text: str, facts: list[Fact], tolerance_frac: float = 0.01) -> list[str]:
    """All numeric problems in a summary: fabricated + misattributed."""
    issues = [
        f"summary number {n:,.0f} is not backed by any fetched fact"
        for n in unsupported_numbers(text, facts, tolerance_frac)
    ]
    issues += attribution_issues(text, facts, tolerance_frac)
    return issues


# --- public gate ----------------------------------------------------------

def verify(answer: Answer, tolerance_frac: float = 0.01) -> list[str]:
    """Return a list of human-readable problems; empty means the answer is clean."""
    issues: list[str] = []

    for f in answer.facts:
        p = f.provenance
        if not p.accession_number or not p.source_url:
            issues.append(f"{f.metric} {f.period}: missing provenance (no filing link)")

    issues += summary_issues(answer.summary, answer.facts, tolerance_frac)
    return issues


def sanitize_summary(
    summary: str, facts: list[Fact], tolerance_frac: float = 0.01
) -> str:
    """Replace numbers that are fabricated *or* misattributed with ``[unverified]``.

    Works line-by-line so a number is checked against the entities named in its
    own line (a markdown-table row names its company and metric in the same row).
    """
    tickers, metrics, by_entity, all_values = _build_index(facts)

    def _sanitize_line(line: str) -> str:
        ct = _detect_tickers(line, tickers)
        cm = _detect_metrics(line, metrics)
        eligible = _eligible_values(by_entity, all_values, ct, cm)

        def _repl(match):
            tok = match.group(0)
            n = parse_number(tok)
            if n is None:
                return tok
            return tok if _matches(n, eligible, tolerance_frac) else "[unverified]"

        return _FIN_NUM_RE.sub(_repl, line)

    return "\n".join(_sanitize_line(line) for line in summary.splitlines())
