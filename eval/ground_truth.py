"""Ground-truth ("oracle") data for the eval.

Built with the *same deterministic extractor* the harness uses, straight from
SEC EDGAR. The harness's numbers must match this exactly; the bare-LLM baseline
will not, which is the whole point of the comparison.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent.edgar import EdgarClient
from agent.extractor import extract_metrics
from agent.schema import Fact

from .questions import Question


@dataclass
class OracleFact:
    ticker: str
    metric: str
    period: str
    value: float
    source_url: str | None = None


def build_oracle(client: EdgarClient, q: Question) -> list[OracleFact]:
    out: list[OracleFact] = []
    for ticker in q.tickers:
        facts: dict[str, list[Fact]] = extract_metrics(
            client, ticker, q.metrics, frequency=q.frequency, n=q.n
        )
        for metric, fs in facts.items():
            for f in fs:
                out.append(
                    OracleFact(
                        ticker=ticker,
                        metric=metric,
                        period=f.period,
                        value=f.provenance.value,
                        source_url=f.provenance.source_url,
                    )
                )
    return out


def build_all_oracles(client: EdgarClient, questions: list[Question]) -> dict[str, list[OracleFact]]:
    return {q.id: build_oracle(client, q) for q in questions}
