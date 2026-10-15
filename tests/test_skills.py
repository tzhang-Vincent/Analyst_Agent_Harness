from agent.skills import describe_skills, load_skills


def test_load_builtin_sector_skills():
    # loads from the project's skills/ directory
    skills = load_skills()
    assert "semiconductor-analysis" in skills
    assert skills["semiconductor-analysis"].sector == "semiconductors"
    assert skills["semiconductor-analysis"].metrics == ["revenue", "rd_expense", "gross_profit"]
    assert "general-health" in skills


def test_load_skills_from_directory(tmp_path):
    (tmp_path / "energy-analysis.yaml").write_text(
        "name: energy-analysis\n"
        "sector: energy\n"
        "description: For energy companies.\n"
        "metrics: [revenue, operating_cash_flow]\n"
        "n_periods: 6\n"
    )
    skills = load_skills(tmp_path)
    assert "energy-analysis" in skills
    assert skills["energy-analysis"].sector == "energy"
    assert skills["energy-analysis"].n_periods == 6


def test_describe_skills():
    skills = load_skills()
    text = describe_skills(skills)
    assert "semiconductor-analysis" in text
    assert "semiconductors" in text
    assert "revenue" in text
