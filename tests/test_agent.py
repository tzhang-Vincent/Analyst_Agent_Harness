from agent.agent import Analyst, parse_intent
from agent.profile import Memory


class FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts
        self._cik = "0001045810"

    def ticker_to_cik(self, ticker):
        return self._cik

    def get_company_facts(self, cik):
        return self._facts


def _qfacts():
    return {
        "entityName": "NVIDIA CORP",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "label": "Revenues",
                    "units": {
                        "USD": [
                            {"start": "2025-04-28", "end": "2025-07-27", "val": 46743000000, "frame": "CY2025Q2", "filed": "2025-08-26", "accn": "a1", "fy": 2026, "fp": "Q2", "form": "10-Q"},
                            {"start": "2025-07-28", "end": "2025-10-26", "val": 57006000000, "frame": "CY2025Q3", "filed": "2025-11-20", "accn": "a2", "fy": 2026, "fp": "Q3", "form": "10-Q"},
                        ]
                    },
                },
                "NetIncomeLoss": {
                    "label": "Net Income",
                    "units": {
                        "USD": [
                            {"start": "2025-04-28", "end": "2025-07-27", "val": 26422000000, "frame": "CY2025Q2", "filed": "2025-08-26", "accn": "a1", "fy": 2026, "fp": "Q2", "form": "10-Q"},
                        ]
                    },
                },
            }
        },
    }


def test_parse_intent_extracts_tickers_metrics_periods():
    intent = parse_intent("compare NVDA AMD INTC revenue and net income over the last 4 quarters")
    assert intent.tickers == ["NVDA", "AMD", "INTC"]
    assert set(intent.metrics) == {"revenue", "net_income"}
    assert intent.frequency == "quarterly"
    assert intent.num_periods == 4


def test_parse_intent_annual():
    intent = parse_intent("NVDA annual revenue and net income")
    assert intent.frequency == "annual"


def test_run_deterministic(tmp_path):
    client = FakeClient(_qfacts())
    memory = Memory(tmp_path)
    analyst = Analyst(client=client, memory=memory)
    answer = analyst.run("NVDA revenue last 2 quarters")

    assert len(answer.facts) == 2
    assert answer.facts[0].metric == "revenue"
    assert "NVDA" in answer.summary
    assert answer.citations  # source URLs present
    # memory updated
    assert "NVDA" in memory.watchlist
    assert memory.preferred_metrics()[0] == "revenue"


def test_run_verifies_clean_deterministic(tmp_path):
    client = FakeClient(_qfacts())
    analyst = Analyst(client=client, memory=Memory(tmp_path))
    answer = analyst.run("NVDA revenue last 2 quarters")
    # deterministic summaries only cite fact values -> verifier must be clean
    assert "[verifier]" not in answer.summary
