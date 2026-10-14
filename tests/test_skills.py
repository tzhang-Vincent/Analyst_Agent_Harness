from agent.skills import load_builtin, load_user_skills, match_skill


def test_builtin_skills_exist():
    skills = load_builtin()
    assert "quarterly-revenue-compare" in skills
    assert "rd-intensity" in skills
    assert skills["rd-intensity"].metrics == ["revenue", "rd_expense"]


def test_load_user_skills(tmp_path):
    (tmp_path / "my-skill.yaml").write_text(
        "name: my-custom-skill\n"
        "description: check operating margin\n"
        "metrics: [revenue, operating_income]\n"
        "frequency: quarterly\n"
        "n_periods: 6\n"
    )
    skills = load_user_skills(tmp_path)
    assert "my-custom-skill" in skills
    assert skills["my-custom-skill"].n_periods == 6


def test_match_skill_keyword():
    skills = load_builtin()
    assert match_skill("compare revenue across quarters for NVDA and AMD", skills).name == "quarterly-revenue-compare"
    assert match_skill("what is the R&D intensity of these chip makers", skills).name == "rd-intensity"
