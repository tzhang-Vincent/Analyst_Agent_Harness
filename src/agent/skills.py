"""Sector skills, loaded from YAML files in ``skills/``.

Each YAML skill declares its ``sector`` and the metrics that matter for it. The
LLM is given the list and *infers* each company's sector itself, then applies
the matching recipe — so sector knowledge lives in editable YAML (and can be
extended by dropping in a new file), not in code.
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


def load_skills(directory: str | Path = "skills") -> dict[str, Skill]:
    """Load every ``*.yaml`` / ``*.yml`` skill from a directory."""
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


def describe_skills(skills: dict[str, Skill]) -> str:
    """A compact text block describing the skills, for injection into an LLM prompt."""
    if not skills:
        return ""
    lines = []
    for s in skills.values():
        lines.append(
            f"- {s.name} [sector: {s.sector}]: {s.description} "
            f"(metrics: {', '.join(s.metrics)})"
        )
    return "\n".join(lines)
