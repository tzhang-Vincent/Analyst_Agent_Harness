"""Sector-scoped analyst recipes ("skills").

Each sector has its own skill, and the skill's description says plainly which
industry it is for. Selection works by *identifying the company's sector* (a
deterministic ticker→sector lookup) and then applying that sector's skill — so
asking about NVDA automatically brings up the semiconductor recipe (R&D
intensity, gross margin), not a generic one.

Users can add more sector skills as YAML files in ``skills/`` (with a ``sector``
field), and can extend the ticker→sector map as they specialize.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Skill:
    name: str
    description: str
    sector: str = "general"
    metrics: list[str] = field(default_factory=list)
    frequency: str = "quarterly"
    n_periods: int = 4
    output_template: str = ""

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "sector": self.sector,
            "metrics": self.metrics,
            "frequency": self.frequency,
            "n_periods": self.n_periods,
            "output_template": self.output_template,
        }


# Which sector a ticker belongs to. This is the deterministic "the agent knows
# what industry each company is in" — a lookup, not an LLM guess, so it cannot
# be hallucinated. Extend as needed.
SECTOR_OF_TICKER: dict[str, str] = {
    # semiconductors
    "NVDA": "semiconductors",
    "AMD": "semiconductors",
    "INTC": "semiconductors",
    "AVGO": "semiconductors",
    "QCOM": "semiconductors",
    "MU": "semiconductors",
    "TSM": "semiconductors",
    # software
    "MSFT": "software",
    # consumer hardware / technology
    "AAPL": "technology",
}


BUILTIN_SKILLS: list[Skill] = [
    Skill(
        "semiconductor-analysis",
        "For semiconductor companies (NVDA, AMD, INTC, TSM, AVGO, ...): focus on "
        "R&D intensity and gross margin — the two key health indicators for chip makers.",
        sector="semiconductors",
        metrics=["revenue", "rd_expense", "gross_profit"],
        frequency="quarterly",
        n_periods=4,
        output_template="R&D expense and gross margin as a share of revenue, by quarter.",
    ),
    Skill(
        "software-analysis",
        "For software companies (MSFT, ...): focus on operating margin and "
        "revenue growth.",
        sector="software",
        metrics=["revenue", "operating_income", "net_income"],
        frequency="quarterly",
        n_periods=4,
        output_template="Revenue, operating income and operating margin, by quarter.",
    ),
    Skill(
        "technology-analysis",
        "For consumer-technology companies (AAPL, ...): focus on gross margin and "
        "cash position.",
        sector="technology",
        metrics=["revenue", "gross_profit", "cash"],
        frequency="quarterly",
        n_periods=4,
        output_template="Revenue, gross margin and cash position, by quarter.",
    ),
    Skill(
        "general-health",
        "General financial health for any company not in a specific sector.",
        sector="general",
        metrics=["revenue", "net_income", "total_assets", "total_liabilities", "cash"],
        frequency="quarterly",
        n_periods=1,
        output_template="Key income-statement and balance-sheet figures for the latest period.",
    ),
]


def load_builtin() -> dict[str, Skill]:
    return {s.name: s for s in BUILTIN_SKILLS}


def load_user_skills(directory: str | Path = "skills") -> dict[str, Skill]:
    """Load user-defined sector skill YAML files from a directory."""
    out: dict[str, Skill] = {}
    d = Path(directory)
    if not d.is_dir():
        return out
    for path in sorted(d.glob("*.yaml")) + sorted(d.glob("*.yml")):
        try:
            data = yaml.safe_load(path.read_text())
            if not isinstance(data, dict) or "name" not in data:
                continue
            out[data["name"]] = Skill(
                name=data["name"],
                description=data.get("description", ""),
                sector=data.get("sector", "general"),
                metrics=data.get("metrics", []),
                frequency=data.get("frequency", "quarterly"),
                n_periods=data.get("n_periods", 4),
                output_template=data.get("output_template", ""),
            )
        except yaml.YAMLError:
            continue
    return out


def load_all(directory: str | Path = "skills") -> dict[str, Skill]:
    skills = load_builtin()
    skills.update(load_user_skills(directory))
    return skills


def sector_of(ticker: str) -> str:
    """The sector a ticker belongs to ('' if unknown)."""
    return SECTOR_OF_TICKER.get(ticker.upper(), "")


def skill_for_tickers(tickers: list[str], skills: dict[str, Skill]) -> Skill | None:
    """The skill matching the sector of the companies being analyzed.

    Deterministic: maps each ticker to its sector, then picks the skill for that
    sector, falling back to the general skill. Returns None only if no skills.
    """
    sectors = {SECTOR_OF_TICKER.get(t) for t in tickers if SECTOR_OF_TICKER.get(t)}
    for skill in skills.values():
        if skill.sector in sectors:
            return skill
    return skills.get("general-health")


def match_skill(query: str, skills: dict[str, Skill]) -> Skill | None:
    """Keyword fallback for procedure-style skills (kept for user YAML)."""
    q = query.lower()
    best: Skill | None = None
    best_score = 0
    for skill in skills.values():
        score = 0
        for token in skill.name.lower().split("-"):
            if token and token in q:
                score += 1
        for word in skill.description.lower().split():
            if word in q:
                score += 1
        if score > best_score:
            best, best_score = skill, score
    return best
