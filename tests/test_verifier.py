from agent.schema import Answer, Fact, Provenance
from agent.verifier import (
    attribution_issues,
    extract_numbers,
    parse_number,
    sanitize_summary,
    verify,
)


def test_parse_number_compact():
    assert parse_number("46.74B") == 46740000000
    assert parse_number("$46,743,000,000") == 46743000000
    assert parse_number("57.0M") == 57000000
    assert parse_number("1.5T") == 1500000000000
    assert parse_number("26422") == 26422


def test_extract_numbers():
    text = "Revenue was $46.74B, up from $44.1B, a 6% increase."
    nums = extract_numbers(text)
    assert 46740000000 in nums
    assert 44100000000 in nums


def test_extract_numbers_ignores_non_financial_tokens():
    # quarter numbers, fiscal years, citation indices and percentages are not values
    text = "NVDA revenue was $46.74B in Q2 FY2026 (+22.0%) [1][2]."
    nums = extract_numbers(text)
    assert nums == [46740000000]


def _fact(value, metric="revenue", accn="a1"):
    return Fact(
        metric=metric,
        period="2025-07-27",
        period_label="Q2 FY2026",
        provenance=Provenance(
            ticker="NVDA",
            cik="0001045810",
            entity_name="NVIDIA CORP",
            xbrl_tag="Revenues",
            xbrl_label="Revenues",
            unit="USD",
            value=value,
            accession_number=accn,
            source_url=f"https://www.sec.gov/Archives/edgar/data/1045810/{accn}/{accn}-index.htm",
        ),
    )


def test_verify_clean_answer():
    answer = Answer(summary="NVDA revenue was $46.74B.", facts=[_fact(46743000000)])
    assert verify(answer) == []


def test_verify_flags_hallucinated_number():
    answer = Answer(
        summary="NVDA revenue was $46.74B and profit was $99.9B.",
        facts=[_fact(46743000000)],
    )
    issues = verify(answer)
    assert any("99" in i for i in issues)


def test_sanitize_summary_replaces_unsupported():
    answer = Answer(
        summary="NVDA revenue was $46.74B and profit was $99.9B.",
        facts=[_fact(46743000000)],
    )
    cleaned = sanitize_summary(answer.summary, answer.facts)
    assert "$46.74B" in cleaned
    assert "$99.9B" not in cleaned
    assert "[unverified]" in cleaned


def _fact_for(ticker, metric, value):
    return Fact(
        metric=metric,
        period="2025-07-27",
        period_label="Q2 FY2026",
        provenance=Provenance(
            ticker=ticker,
            cik="0001045810",
            entity_name="CO",
            xbrl_tag="Revenues",
            xbrl_label="Revenues",
            unit="USD",
            value=value,
            accession_number="a1",
            source_url="https://www.sec.gov/Archives/edgar/data/1045810/a1/a1-index.htm",
        ),
    )


def test_attribution_issues_catches_misattribution():
    facts = [
        _fact_for("NVDA", "revenue", 46743000000),
        _fact_for("AMD", "revenue", 11540000000),
    ]
    # $46.74B is NVDA's revenue, but the prose attributes it to AMD
    issues = attribution_issues("AMD revenue was $46.74B.", facts)
    assert any("AMD" in i for i in issues)


def test_attribution_issues_clean_when_correct():
    facts = [
        _fact_for("NVDA", "revenue", 46743000000),
        _fact_for("AMD", "revenue", 11540000000),
    ]
    assert attribution_issues("NVDA revenue was $46.74B.", facts) == []
    assert attribution_issues("AMD revenue was $11.54B.", facts) == []


def test_sanitize_removes_misattributed_number():
    facts = [
        _fact_for("NVDA", "revenue", 46743000000),
        _fact_for("AMD", "revenue", 11540000000),
    ]
    cleaned = sanitize_summary("AMD revenue was $46.74B.", facts)
    assert "$46.74B" not in cleaned
    assert "[unverified]" in cleaned


def test_verify_flags_missing_provenance():
    f = _fact(46743000000)
    f.provenance.accession_number = None
    f.provenance.source_url = None
    answer = Answer(summary="NVDA revenue was $46.74B.", facts=[f])
    assert any("provenance" in i for i in verify(answer))
