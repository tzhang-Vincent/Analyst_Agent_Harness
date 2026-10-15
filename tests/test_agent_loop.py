from agent.agent_loop import _seed_messages, execute_tool


def test_seed_messages_with_history():
    history = [
        {"role": "user", "content": "NVDA revenue"},
        {"role": "assistant", "content": "NVDA revenue was ..."},
    ]
    msgs = _seed_messages("compare with AMD", history)
    assert msgs[0] == {"role": "user", "content": "NVDA revenue"}
    assert msgs[-1] == {"role": "user", "content": "compare with AMD"}
    assert len(msgs) == 3


def test_seed_messages_no_history():
    assert _seed_messages("NVDA revenue", None) == [{"role": "user", "content": "NVDA revenue"}]


class FakeClient:
    def __init__(self, facts):
        self._facts = facts

    def ticker_to_cik(self, ticker):
        if ticker in ("NVDA", "AMD"):
            return "0001045810"
        raise KeyError(ticker)

    def get_company_facts(self, cik):
        return self._facts


def _facts():
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
                }
            }
        },
    }


def test_execute_tool_drops_invalid_metric():
    client = FakeClient(_facts())
    result = execute_tool(
        "get_metrics", {"ticker": "NVDA", "metrics": ["revenue", "bogus_metric"], "n": 2}, client
    )
    assert all(f.metric == "revenue" for f in result["facts"])
    assert len(result["facts"]) == 2


def test_execute_tool_drops_invalid_ticker():
    client = FakeClient(_facts())
    result = execute_tool("get_metrics", {"ticker": "ZZZZ", "metrics": ["revenue"]}, client)
    assert result["facts"] == []
    assert result["facts_by_company"] == {}


def test_execute_tool_compare_companies():
    client = FakeClient(_facts())
    result = execute_tool(
        "compare_companies", {"tickers": ["NVDA", "ZZZZ"], "metrics": ["revenue"], "n": 2}, client
    )
    tickers = {f.provenance.ticker for f in result["facts"]}
    assert tickers == {"NVDA"}  # ZZZZ dropped
