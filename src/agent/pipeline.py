"""The pipeline mode: deterministic orchestration with the LLM at fixed steps.

intent (rule + optional LLM, validated) -> skill -> deterministic extraction ->
summary (template, or LLM constrained to the facts) -> verifier -> memory.

The numbers and their provenance come from the deterministic extractor; the LLM
only parses intent and writes the summary, never generates a number.
"""

from __future__ import annotations

import json
import re

from .edgar import EdgarClient
from .extractor import extract_metrics
from .llm import LLM
from .metrics import ALIASES, canonical_metric, metric_label
from .profile import Memory
from .schema import Answer, QueryIntent
from .skills import match_skill
from .table import flatten, fmt_compact
from .verifier import sanitize_summary, verify

DEFAULT_TICKERS = {"NVDA", "AMD", "INTC", "MSFT", "AAPL", "TSM", "AVGO", "QCOM", "MU"}
_TICKER_RE = re.compile(r"\b[A-Z]{1,5}\b")
_PERIOD_RE = re.compile(r"last (\d+)\s*(quarters?|years?|periods?)", re.IGNORECASE)

# Words that look like 1-5 letter ticker candidates in a query but are almost
# never meant as tickers there — English function words ("and" is also a real
# ticker) plus financial terms ("cash", "net", "flow", ...).
_STOPWORDS = {
    "A", "AN", "AND", "ARE", "AS", "AT", "BE", "BY", "COMPARE", "EACH", "FOR",
    "FROM", "HOW", "IN", "IS", "IT", "LAST", "MUCH", "NEXT", "OF", "OR",
    "OVER", "PAST", "RECENT", "SHOW", "THAT", "THE", "THIS", "TO", "VS",
    "WAS", "WHAT", "WHICH", "WITH",
    "ASSETS", "CASH", "COST", "DEBT", "DILUTED", "EARNINGS", "EPS", "EQUITY",
    "EXPENSE", "EXPENSES", "FLOW", "GROSS", "GROWTH", "INCOME", "LIABILITIES",
    "MARGIN", "NET", "OPERATING", "OPERATIONS", "PROFIT", "RATIO", "RD",
    "REVENUE", "SALES", "SHARES", "TOTAL",
}

# Aliases that need a negative lookahead so a short word does not also match a
# longer phrase containing it (e.g. "cash" inside "cash flow").
_SPECIAL_PATTERNS = {
    "cash": r"\bcash\b(?!\s*flow)",
}

_INTENT_SYSTEM = (
    "Extract the companies and financial metrics from the analyst's question. "
    'Respond with ONLY a JSON object, no prose, shaped like '
    '{"tickers":["NVDA"],"metrics":["revenue"],"num_periods":4,"frequency":"quarterly"}. '
    "- tickers: UPPERCASE stock symbols (NVDA, not 'Nvidia'); [] if none. "
    "- metrics: canonical keys only, from revenue, net_income, gross_profit, "
    "operating_income, rd_expense, cost_of_revenue, total_assets, total_liabilities, "
    "cash, operating_cash_flow, diluted_eps, shares_outstanding; map user phrasing "
    "to the closest key ('profitability' -> net_income); [] if none. "
    "- num_periods: integer (default 4). "
    "- frequency: 'quarterly' or 'annual'."
)


def _parse_json_obj(text: str) -> dict:
    """Parse a JSON object out of LLM output, tolerating markdown fences/prose."""
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return {}


def _extract_metrics(query_lower: str) -> list[str]:
    found: list[str] = []
    text = query_lower
    # Longest alias first, and blank out the matched span, so "gross profit"
    # does not also fire "profit" (net_income) or "earnings" inside
    # "earnings per share".
    for alias, key in sorted(ALIASES.items(), key=lambda kv: -len(kv[0])):
        pattern = _SPECIAL_PATTERNS.get(alias, r"\b" + re.escape(alias) + r"\b")
        m = re.search(pattern, text)
        if m and key not in found:
            found.append(key)
            text = text[: m.start()] + " " * (m.end() - m.start()) + text[m.end():]
    return found


def _resolve_tickers(candidates: list[str], client: EdgarClient | None, known: set[str]) -> list[str]:
    """Keep candidate tokens that are real tickers (validated against SEC if possible)."""
    out: list[str] = []
    for t in candidates:
        if t in _STOPWORDS:
            continue
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
    if re.search(r"annual|yearly|fiscal year|full year|\byears?\b", q) and not re.search(
        r"year[\s-]over[\s-]year|\byoy\b|\by/y\b", q
    ):
        intent.frequency = "annual"
    m = _PERIOD_RE.search(q)
    if m:
        intent.num_periods = int(m.group(1))

    known = set(memory.watchlist if memory else []) | DEFAULT_TICKERS
    # Strip possessives so "NVDA's" doesn't leak "S" as a 1-letter ticker.
    cleaned = query.upper().replace("'S", " ").replace("'", " ")
    candidates = _TICKER_RE.findall(cleaned)
    intent.tickers = _resolve_tickers(candidates, client, known)
    return intent


class PipelineRunner:
    def __init__(
        self,
        client: EdgarClient,
        memory: Memory,
        llm: LLM | None,
        skills: dict,
        use_llm_intent: bool = True,
    ) -> None:
        self.client = client
        self.memory = memory
        self.llm = llm
        self.skills = skills
        self.use_llm_intent = use_llm_intent
        self.last_intent: QueryIntent | None = None

    def run(self, query: str) -> Answer:
        intent = self._resolve(query)
        self.last_intent = intent

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

        summary, citations = self._summarize(intent, facts_by_company)
        answer = Answer(
            summary=summary,
            facts=flatten(facts_by_company),
            citations=citations,
        )

        issues = verify(answer)
        if issues:
            answer.summary = sanitize_summary(summary, answer.facts)
            answer.summary += (
                "\n\n[verifier] flagged unsupported numeric claims "
                "(shown as [unverified]):\n"
                + "\n".join(f"  - {i}" for i in issues)
            )

        self._remember(intent, query)
        return answer

    # -- intent ------------------------------------------------------------
    def _resolve(self, query: str) -> QueryIntent:
        det = parse_intent(query, self.memory, self.client)
        if self.llm is None or not self.use_llm_intent:
            return det
        fields = self._llm_intent_fields(query)
        return QueryIntent(
            raw_query=query,
            tickers=fields.get("tickers", det.tickers),
            metrics=fields.get("metrics", det.metrics),
            frequency=fields.get("frequency", det.frequency),
            num_periods=fields.get("num_periods", det.num_periods),
        )

    def _llm_intent_fields(self, query: str) -> dict:
        """Ask the LLM to parse the query; return validated fields ({} on failure).

        Tickers are validated against the SEC ticker map and metrics against the
        metric registry, so an LLM mis-parse cannot inject a wrong company/metric.
        """
        try:
            resp = self.llm.chat(
                [
                    {"role": "system", "content": _INTENT_SYSTEM},
                    {"role": "user", "content": query},
                ]
            )
            args = _parse_json_obj(resp.get("content") or "")
        except Exception:
            return {}

        out: dict = {}
        tickers: list[str] = []
        for t in args.get("tickers") or []:
            t = str(t).upper()
            try:
                self.client.ticker_to_cik(t)
                tickers.append(t)
            except KeyError:
                continue
        if tickers:
            out["tickers"] = tickers

        metrics: list[str] = []
        for m in args.get("metrics") or []:
            key = canonical_metric(str(m))
            if key and key not in metrics:
                metrics.append(key)
        if metrics:
            out["metrics"] = metrics

        freq = args.get("frequency")
        if freq in ("quarterly", "annual"):
            out["frequency"] = freq
        n = args.get("num_periods")
        if isinstance(n, int) and 1 <= n <= 20:
            out["num_periods"] = n
        return out

    # -- summary -----------------------------------------------------------
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
                    if first.provenance.value:
                        pct = (last.provenance.value - first.provenance.value) / first.provenance.value * 100
                        change = f" ({pct:+.1f}%)"
                    else:
                        change = ""
                    lines.append(
                        f"{ticker} {label}: {fmt_compact(last.provenance.value)} in "
                        f"{last.period_label} vs {fmt_compact(first.provenance.value)} in "
                        f"{first.period_label}{change} [{idx0}][{idx}]"
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
