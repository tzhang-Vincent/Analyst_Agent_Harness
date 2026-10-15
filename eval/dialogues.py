"""Multi-turn conversation eval: dialogues with per-turn ground truth.

Each turn's ``tickers`` / ``metrics`` / ``frequency`` / ``n`` encode the
*correct* reference resolution for that turn, given the conversation so far.
For example, in "NVDA revenue" then "compare it with AMD", turn 2's tickers are
``["NVDA", "AMD"]`` because "it" must resolve back to NVDA. The same per-turn
metrics (coverage / precision / provenance / hallucination) then measure whether
the agent resolved the reference and stayed traceable.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Turn:
    text: str
    tickers: list[str]
    metrics: list[str]
    frequency: str = "quarterly"
    n: int = 4


@dataclass
class Dialogue:
    id: str
    turns: list[Turn]


DIALOGUES: list[Dialogue] = [
    Dialogue(
        "d1-ellipsis",
        [
            Turn("What was NVDA's revenue in the last 4 quarters?", ["NVDA"], ["revenue"]),
            Turn("Now compare it with AMD.", ["NVDA", "AMD"], ["revenue"]),
            Turn("Which of the two grew faster over that period?", ["NVDA", "AMD"], ["revenue"]),
        ],
    ),
    Dialogue(
        "d2-metric-carry",
        [
            Turn("What was MSFT's net income in the last 4 quarters?", ["MSFT"], ["net_income"]),
            Turn("What about its gross profit?", ["MSFT"], ["gross_profit"]),
        ],
    ),
    Dialogue(
        "d3-period-carry",
        [
            Turn(
                "What was NVDA's annual revenue for the last 2 fiscal years?",
                ["NVDA"], ["revenue"], frequency="annual", n=2,
            ),
            Turn("Same for AMD.", ["AMD"], ["revenue"], frequency="annual", n=2),
        ],
    ),
    Dialogue(
        "d4-cross-company-context",
        [
            Turn(
                "Compare AMD revenue and net income over the last 4 quarters.",
                ["AMD"], ["revenue", "net_income"],
            ),
            Turn("Now do the same for INTC.", ["INTC"], ["revenue", "net_income"]),
        ],
    ),
]
