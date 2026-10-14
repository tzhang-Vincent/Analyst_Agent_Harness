"""Reusable analyst recipes ("skills").

Two layers, on purpose:

- **tools** are the atomic deterministic data primitives (get a fact, get an
  income statement). The LLM picks which to call.
- **skills** are higher-level recipes that bundle sector knowledge (which
  metrics matter), a fixed tool sequence, and an output template. This is where
  sector specialization lives, and users can add their own YAML recipes in
  ``skills/`` so the agent accumulates capability over time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Skill:
    name: str
    description: str
    metrics: list[str] = field(default_factory=list)
    frequency: str = "quarterly"
    n_periods: int = 4
    output_template: str = ""

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "metrics": self.metrics,
            "frequency": self.frequency,
            "n_periods": self.n_periods,
            "output_template": self.output_template,
        }


BUILTIN_SKILLS: list[Skill] = [
    Skill(
        "quarterly-revenue-compare",
        "Compare revenue and net income across the last N quarters for a set of companies.",
        metrics=["revenue", "net_income"],
        frequency="quarterly",
        n_periods=4,
        output_template="Comparison table with one row per company/metric and columns per quarter, plus a short trend summary.",
    ),
    Skill(
        "rd-intensity",
        "R&D intensity (R&D expense as a share of revenue) — a key semiconductor metric.",
        metrics=["revenue", "rd_expense"],
        frequency="quarterly",
        n_periods=4,
        output_template="Table of R&D expense and R&D/revenue ratio by quarter.",
    ),
    Skill(
        "gross-margin-trend",
        "Gross margin trend over recent quarters.",
        metrics=["revenue", "gross_profit"],
        frequency="quarterly",
        n_periods=4,
        output_template="Table of revenue, gross profit and gross margin % by quarter.",
    ),
    Skill(
        "trace-a-number",
        "Trace a single number back to the exact SEC filing that reported it.",
        metrics=[],
        frequency="quarterly",
        n_periods=1,
        output_template="The value plus its full provenance record (tag, accession, filing URL).",
    ),
]


def load_builtin() -> dict[str, Skill]:
    return {s.name: s for s in BUILTIN_SKILLS}


def load_user_skills(directory: str | Path = "skills") -> dict[str, Skill]:
    """Load user-defined skill YAML files from a directory."""
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


def match_skill(query: str, skills: dict[str, Skill]) -> Skill | None:
    """Best keyword match of a query against skill names/descriptions."""
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
