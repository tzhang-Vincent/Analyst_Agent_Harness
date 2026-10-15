"""User preference memory.

"Adapt to the user over time" = load memory before answering, use it to bias
behavior (watchlist, preferred metrics, output style), then persist what was
learned after the interaction. Three kinds of memory, each a JSON file:

- ``preferences.json`` — who the user is (watchlist, preferred metrics, output).
- ``interactions.json`` — what happened (queries, user corrections).
- ``knowledge.json`` — what was learned (cached facts, e.g. fiscal year-ends).
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_PREFERENCES: dict = {
    "watchlist": ["NVDA", "AMD", "INTC", "MSFT", "AAPL"],
    "preferred_metrics": ["revenue", "net_income", "gross_profit", "rd_expense"],
    "output": {"frequency": "quarterly", "export": "xlsx"},
    "sector": "technology",
}


class Memory:
    def __init__(self, base_dir: str | Path = "data/memory") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.preferences = self._load("preferences.json", DEFAULT_PREFERENCES)
        self.interactions = self._load(
            "interactions.json", {"queries": [], "corrections": []}
        )
        self.knowledge = self._load("knowledge.json", {})

    # -- io ---------------------------------------------------------------
    def _load(self, name: str, default):
        path = self.base_dir / name
        if path.exists():
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                return default
        return default

    def _save(self, name: str, data) -> None:
        (self.base_dir / name).write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def save(self) -> None:
        self._save("preferences.json", self.preferences)
        self._save("interactions.json", self.interactions)
        self._save("knowledge.json", self.knowledge)

    # -- preferences ------------------------------------------------------
    @property
    def watchlist(self) -> list[str]:
        return self.preferences.get("watchlist", [])

    def add_tickers(self, tickers) -> None:
        for t in tickers:
            t = t.upper()
            if t not in self.preferences["watchlist"]:
                self.preferences["watchlist"].append(t)

    def bump_metric(self, metric: str) -> None:
        """Move a metric to the front of preferred metrics (recently used)."""
        m = self.preferences.setdefault("preferred_metrics", [])
        if metric in m:
            m.remove(metric)
        m.insert(0, metric)

    def preferred_metrics(self, fallback: list[str] | None = None) -> list[str]:
        return self.preferences.get("preferred_metrics") or fallback or []

    # -- interactions -----------------------------------------------------
    def record_query(self, query: str, tickers: list[str], metrics: list[str]) -> None:
        self.interactions.setdefault("queries", []).append(
            {"query": query, "tickers": tickers, "metrics": metrics}
        )
        self.interactions["queries"] = self.interactions["queries"][-100:]

    def record_correction(self, feedback: str) -> None:
        self.interactions.setdefault("corrections", []).append({"feedback": feedback})
        self.interactions["corrections"] = self.interactions["corrections"][-100:]

    def corrections(self) -> list[dict]:
        return self.interactions.get("corrections", [])

    def recent_corrections(self, n: int = 5) -> list[str]:
        """The last ``n`` user corrections, as plain strings (for prompt injection)."""
        return [c.get("feedback", "") for c in self.corrections()[-n:]]

    # -- knowledge --------------------------------------------------------
    def remember(self, key: str, value) -> None:
        self.knowledge[key] = value

    def recall(self, key: str):
        return self.knowledge.get(key)
