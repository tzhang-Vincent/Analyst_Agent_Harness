from agent.edgar import EdgarClient, filing_index_url


def test_filing_index_url_format():
    url = filing_index_url("0001045810", "0001045810-19-000023")
    assert url == (
        "https://www.sec.gov/Archives/edgar/data/1045810/"
        "000104581019000023/0001045810-19-000023-index.htm"
    )


def test_ticker_to_cik_zero_padding():
    client = EdgarClient(cache_dir="/tmp/nonexistent-edgar-cache")
    client._ticker_map = {
        "0": {"ticker": "NVDA", "cik_str": 1045810},
        "1": {"ticker": "MSFT", "cik_str": 789019},
    }
    assert client.ticker_to_cik("nvda") == "0001045810"
    assert client.ticker_to_cik("MSFT") == "0000789019"


def test_ticker_to_cik_unknown():
    client = EdgarClient(cache_dir="/tmp/nonexistent-edgar-cache")
    client._ticker_map = {"0": {"ticker": "NVDA", "cik_str": 1045810}}
    try:
        client.ticker_to_cik("ZZZZ")
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError for unknown ticker")


def test_cached_get_writes_and_reads(monkeypatch, tmp_path):
    client = EdgarClient(cache_dir=tmp_path)
    calls = {"n": 0}

    def fake_get(url):
        calls["n"] += 1
        return {"url": url}

    monkeypatch.setattr(client, "_get", fake_get)
    first = client._cached_get("k", "http://x")
    second = client._cached_get("k", "http://x")
    assert first == {"url": "http://x"}
    assert second == {"url": "http://x"}
    assert calls["n"] == 1  # second read came from cache
