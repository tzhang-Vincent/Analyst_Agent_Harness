from agent.profile import Memory


def test_add_tickers_dedup_and_upper(tmp_path):
    m = Memory(tmp_path)
    m.add_tickers(["tsm", "NVDA", "tsm"])
    assert m.watchlist.count("TSM") == 1
    assert m.watchlist[0] == "NVDA"  # default watchlist already had NVDA
    assert "TSM" in m.watchlist


def test_bump_metric_moves_to_front(tmp_path):
    m = Memory(tmp_path)
    m.bump_metric("rd_expense")
    assert m.preferred_metrics()[0] == "rd_expense"


def test_record_query_caps_history(tmp_path):
    m = Memory(tmp_path)
    for i in range(150):
        m.record_query(f"q{i}", ["NVDA"], ["revenue"])
    assert len(m.interactions["queries"]) == 100


def test_save_and_reload_roundtrip(tmp_path):
    m = Memory(tmp_path)
    m.add_tickers(["AMD"])
    m.remember("NVDA_fy_end_month", 1)
    m.save()

    m2 = Memory(tmp_path)
    assert "AMD" in m2.watchlist
    assert m2.recall("NVDA_fy_end_month") == 1


def test_corrections(tmp_path):
    m = Memory(tmp_path)
    m.record_correction("I want annual data, not quarterly")
    assert m.corrections()[0]["feedback"] == "I want annual data, not quarterly"


def test_recent_corrections(tmp_path):
    m = Memory(tmp_path)
    m.record_correction("annual data")
    m.record_correction("use net income")
    assert m.recent_corrections(1) == ["use net income"]
    assert m.recent_corrections() == ["annual data", "use net income"]
