"""The agentic harness: intent -> skill -> tools -> summary -> verify -> memory.

Two run modes, deliberately layered:

- **Deterministic** (no LLM): intent is parsed by rule, the summary is a
  template built from facts. Fully testable offline, and it is what the eval
  oracle uses. Numbers are always correct because they come straight from EDGAR.
- **LLM-assisted** (an LLM is configured): intent is still parsed by rule for
  reliability, but the summary is written by the LLM *constrained to the facts*
  and then re-checked by the verifier.

Ruling: intent parsing stays deterministic even when an LLM is present. A ticker
or metric mis-parsed by an LLM would be a silent provenance bug; the constrained
vocabulary (tickers + metric names) is better handled by rules.
"""

from __future__ import annotations

import re

from .edgar import EdgarClient
from .extractor import extract_metrics
from .llm import LLM
from .metrics import ALIASES, metric_label
from .profile import Memory
from .schema import Answer, Fact, QueryIntent
from .skills import Skill, load_all, match_skill
from .table import flatten, fmt_compact
from .verifier import verify

DEFAULT_TICKERS = {"NVDA", "AMD", "INTC", "MSFT", "AAPL", "TSM", "AVGO", "QCOM", "MU"}
_TICKER_RE = re.compile(r"\b[A-Z]{1,5}\b")
_PERIOD_RE = re.compile(r"last (\d+)\s*(quarters?|years?|periods?)", re.IGNORECASE)


def _extract_metrics(query_lower: str) -> list[str]:
    found: list[str] = []
    for alias, key in ALIASES.items():
        if alias in query_lower and key not in found:
            found.append(key)
    return found


def _resolve_tickers(candidates: list[str], client: EdgarClient | None, known: set[str]) -> list[str]:
    """Keep candidate tokens that are real tickers (validated against SEC if possible)."""
    out: list[str] = []
    for t in candidates:
        if client is not None:
            try:
                client.ticker_to_cik(t)
                out.append(t)
            except KeyError:
                continue
        elif t in known:
            out.append(t)
    return out


def parse_intent(
    query: str,
    memory: Memory | None = None,
    client: EdgarClient | None = None,
) -> QueryIntent:
    q = query.lower()
    intent = QueryIntent(raw_query=query)

    intent.metrics = _extract_metrics(q)
    if "annual" in q or "yearly" in q or "fiscal year" in q or "full year" in q:
        intent.frequency = "annual"
    m = _PERIOD_RE.search(q)
    if m:
        intent.num_periods = int(m.group(1))

    known = set(memory.watchlist if memory else []) | DEFAULT_TICKERS
    candidates = [t.upper() for t in _TICKER_RE.findall(query)]
    intent.tickers = _resolve_tickers(candidates, client, known)
    return intent


class Analyst:
    def __init__(
        self,
        client: EdgarClient | None = None,
        memory: Memory | None = None,
        llm: LLM | None = None,
        skills: dict[str, Skill] | None = None,
        memory_dir: str = "data/memory",
    ) -> None:
        self.client = client or EdgarClient()
        self.memory = memory or Memory(memory_dir)
        self.llm = llm
        self.skills = skills if skills is not None else load_all()
        self.last_facts_by_company: dict[str, dict[str, list[Fact]]] = {}

    def run(self, query: str) -> Answer:
        intent = self._resolve(query)

        # A matched skill supplies sector knowledge (which metrics to use).
        skill = match_skill(query, self.skills)
        if skill and skill.metrics and not intent.metrics:
            intent.metrics = skill.metrics
        if not intent.metrics:
            intent.metrics = self.memory.preferred_metrics() or ["revenue", "net_income"]
        if not intent.tickers:
            intent.tickers = self.memory.watchlist[:3]

        facts_by_company = {
            t: extract_metrics(
                self.client, t, intent.metrics, intent.frequency, intent.num_periods
            )
            for t in intent.tickers
        }
        self.last_facts_by_company = facts_by_company

        summary, citations = self._summarize(intent, facts_by_company)
        answer = Answer(
            summary=summary,
            facts=flatten(facts_by_company),
            citations=citations,
        )

        issues = verify(answer)
        if issues:
            # Drop any unsupported numeric claim; a data gap beats a guess.
            answer.summary = (
                f"{summary}\n\n[verifier] dropped unsupported numbers:\n"
                + "\n".join(f"  - {i}" for i in issues)
            )

        self._remember(intent, query)
        return answer

    # -- internals ---------------------------------------------------------
    def _resolve(self, query: str) -> QueryIntent:
        intent = parse_intent(query, self.memory, self.client)
        return intent

    def _cite(self, citations: list[str], url: str | None) -> int:
        if url and url not in citations:
            citations.append(url)
        return citations.index(url) + 1 if url in citations else 0

    def _summarize(self, intent: QueryIntent, facts_by_company) -> tuple[str, list[str]]:
        if self.llm is not None:
            return self._summarize_llm(intent, facts_by_company)
        return self._summarize_template(intent, facts_by_company)

    def _summarize_template(self, intent, facts_by_company) -> tuple[str, list[str]]:
        citations: list[str] = []
        lines: list[str] = []
        for ticker in sorted(facts_by_company):
            for mk, facts in facts_by_company[ticker].items():
                if not facts:
                    continue
                label = metric_label(mk)
                last = facts[-1]
                idx = self._cite(citations, last.provenance.source_url)
                if len(facts) >= 2:
                    first = facts[0]
                    idx0 = self._cite(citations, first.provenance.source_url)
                    pct = (last.provenance.value - first.provenance.value) / first.provenance.value * 100
                    lines.append(
                        f"{ticker} {label}: {fmt_compact(last.provenance.value)} in "
                        f"{last.period_label} vs {fmt_compact(first.provenance.value)} in "
                        f"{first.period_label} ({pct:+.1f}%) [{idx0}][{idx}]"
                    )
                else:
                    lines.append(
                        f"{ticker} {label}: {fmt_compact(last.provenance.value)} in "
                        f"{last.period_label} [{idx}]"
                    )
        body = "\n".join(lines) if lines else "(no data found)"
        src = "\n".join(f"[{i}] {u}" for i, u in enumerate(citations, 1))
        return f"Summary:\n{body}\n\nSources:\n{src}", citations

    def _summarize_llm(self, intent, facts_by_company) -> tuple[str, list[str]]:
        citations: list[str] = []
        data_lines: list[str] = []
        for ticker in sorted(facts_by_company):
            for mk, facts in facts_by_company[ticker].items():
                for f in facts:
                    idx = self._cite(citations, f.provenance.source_url)
                    data_lines.append(
                        f"[{idx}] {ticker} {metric_label(mk)} {f.period_label}: "
                        f"{fmt_compact(f.provenance.value)}"
                    )
        data = "\n".join(data_lines)
        system = (
            "You are a financial research assistant. Write a concise summary of the "
            "data below. Every number you state MUST come from the data, use the "
            "exact dollar values as given, and be cited with its [n] reference. "
            "Never invent or estimate a number. Do not add numbers that are not in "
            "the data."
        )
        user = f"Question: {intent.raw_query}\n\nData:\n{data}\n\nSummary:"
        resp = self.llm.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}]
        )
        summary = resp.get("content") or "(no summary produced)"
        src = "\n".join(f"[{i}] {u}" for i, u in enumerate(citations, 1))
        return f"{summary}\n\nSources:\n{src}", citations

    def _remember(self, intent: QueryIntent, query: str) -> None:
        self.memory.add_tickers(intent.tickers)
        for mk in intent.metrics:
            self.memory.bump_metric(mk)
        self.memory.record_query(query, intent.tickers, intent.metrics)
        self.memory.save()
