from agent.analyst import Analyst
from agent.pipeline import parse_intent
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


def test_parse_intent_lowercase_ticker():
    intent = parse_intent("nvda revenue last 2 quarters")
    assert intent.tickers == ["NVDA"]
    assert intent.metrics == ["revenue"]


def test_parse_intent_last_years_is_annual():
    intent = parse_intent("NVDA revenue over the last 4 years")
    assert intent.frequency == "annual"
    assert intent.num_periods == 4


def test_parse_intent_cash_flow_not_balance_sheet_cash():
    intent = parse_intent("cash flow from operations for NVDA")
    assert intent.metrics == ["operating_cash_flow"]
    # "cash"/"flow" must not leak in as tickers
    assert intent.tickers == ["NVDA"]


def test_parse_intent_rd_not_substring_match():
    # "rd" must not match inside "record" / "third"
    intent = parse_intent("NVDA record revenue for the third quarter")
    assert "rd_expense" not in intent.metrics


def test_parse_intent_possessive_apostrophe_does_not_leak_ticker():
    # "NVDA's" must not leak "S" (a real 1-letter ticker) as a second company
    intent = parse_intent("What was NVDA's revenue in the last 4 quarters?")
    assert intent.tickers == ["NVDA"]


def test_parse_intent_gross_profit_does_not_also_match_profit():
    intent = parse_intent("AAPL gross profit over the last 4 quarters")
    assert intent.metrics == ["gross_profit"]


def test_parse_intent_earnings_per_share_not_net_income():
    intent = parse_intent("MSFT earnings per share last 4 quarters")
    assert intent.metrics == ["diluted_eps"]


class ValidatingFakeClient(FakeClient):
    """FakeClient that only resolves a known set of tickers (rejects others)."""

    VALID = {"NVDA", "AMD", "INTC", "MSFT", "AAPL"}

    def ticker_to_cik(self, ticker):
        if ticker in self.VALID:
            return self._cik
        raise KeyError(ticker)


class FakeLLM:
    def __init__(self, result):
        self._result = result

    def chat(self, messages, tools=None, tool_choice=None):
        return self._result


def _llm_resp(args):
    import json as _json

    return {"role": "assistant", "content": _json.dumps(args), "tool_calls": []}


def test_llm_intent_overrides_and_fills_gaps(tmp_path):
    client = ValidatingFakeClient(_qfacts())
    llm = FakeLLM(_llm_resp({"tickers": ["NVDA", "MSFT"], "metrics": ["revenue", "net_income"], "num_periods": 3}))
    analyst = Analyst(client=client, memory=Memory(tmp_path), llm=llm)
    intent = analyst.pipeline._resolve("profitability of NVDA and MSFT")
    assert intent.tickers == ["NVDA", "MSFT"]
    assert intent.metrics == ["revenue", "net_income"]
    assert intent.num_periods == 3


def test_llm_intent_invalid_ticker_dropped(tmp_path):
    client = ValidatingFakeClient(_qfacts())
    llm = FakeLLM(_llm_resp({"tickers": ["NVDA", "ZZZZ"], "metrics": ["revenue"]}))
    analyst = Analyst(client=client, memory=Memory(tmp_path), llm=llm)
    intent = analyst.pipeline._resolve("NVDA revenue")
    assert intent.tickers == ["NVDA"]  # ZZZZ not a real ticker -> dropped
    assert intent.metrics == ["revenue"]


def test_llm_intent_fallback_on_error(tmp_path):
    class BoomLLM:
        def chat(self, *a, **k):
            raise RuntimeError("boom")

    client = ValidatingFakeClient(_qfacts())
    analyst = Analyst(client=client, memory=Memory(tmp_path), llm=BoomLLM())
    intent = analyst.pipeline._resolve("NVDA revenue last 2 quarters")
    assert intent.tickers == ["NVDA"]
    assert intent.metrics == ["revenue"]
    assert intent.num_periods == 2


def test_llm_intent_fallback_when_empty(tmp_path):
    client = ValidatingFakeClient(_qfacts())
    llm = FakeLLM(_llm_resp({"tickers": [], "metrics": []}))
    analyst = Analyst(client=client, memory=Memory(tmp_path), llm=llm)
    intent = analyst.pipeline._resolve("NVDA revenue last 2 quarters")
    assert intent.tickers == ["NVDA"]  # deterministic fallback
    assert intent.metrics == ["revenue"]


def test_run_zero_first_value_no_crash(tmp_path):
    data = {
        "entityName": "CO",
        "facts": {"us-gaap": {
            "Revenues": {"label": "Revenues", "units": {"USD": [
                {"start": "2023-01-01", "end": "2023-03-31", "val": 0, "frame": "CY2023Q1", "filed": "2023-05-01", "accn": "z1", "fy": 2023, "fp": "Q1", "form": "10-Q"},
                {"start": "2023-04-01", "end": "2023-06-30", "val": 1000000, "frame": "CY2023Q2", "filed": "2023-08-01", "accn": "z2", "fy": 2023, "fp": "Q2", "form": "10-Q"},
            ]}},
        }},
    }
    client = FakeClient(data)
    analyst = Analyst(client=client, memory=Memory(tmp_path))
    answer = analyst.run("CO revenue")
    assert "CO" in answer.summary  # no ZeroDivisionError
