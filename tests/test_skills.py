from agent.skills import (
    load_builtin,
    load_user_skills,
    sector_of,
    skill_for_tickers,
)


def test_builtin_skills_have_sectors():
    skills = load_builtin()
    assert "semiconductor-analysis" in skills
    assert skills["semiconductor-analysis"].sector == "semiconductors"
    assert skills["semiconductor-analysis"].metrics == ["revenue", "rd_expense", "gross_profit"]


def test_sector_of():
    assert sector_of("NVDA") == "semiconductors"
    assert sector_of("msft") == "software"
    assert sector_of("UNKNOWN") == ""


def test_skill_for_tickers_matches_sector():
    skills = load_builtin()
    assert skill_for_tickers(["NVDA"], skills).sector == "semiconductors"
    assert skill_for_tickers(["MSFT"], skills).sector == "software"
    assert skill_for_tickers(["AAPL"], skills).sector == "technology"


def test_skill_for_tickers_falls_back_to_general():
    skills = load_builtin()
    assert skill_for_tickers(["SOME_UNKNOWN_TICKER"], skills).sector == "general"


def test_load_user_skills_reads_sector(tmp_path):
    (tmp_path / "my-skill.yaml").write_text(
        "name: my-custom-skill\n"
        "sector: energy\n"
        "description: check operating margin\n"
        "metrics: [revenue, operating_income]\n"
        "n_periods: 6\n"
    )
    skills = load_user_skills(tmp_path)
    assert "my-custom-skill" in skills
    assert skills["my-custom-skill"].sector == "energy"
    assert skills["my-custom-skill"].n_periods == 6
