"""The Analyst: the top-level entry point, dispatching between the two modes.

- **pipeline** (deterministic orchestration): see :mod:`.pipeline`.
- **agent** (the LLM drives tool calls): see :mod:`.agent_loop`.

Both share the deterministic data layer and the verifier; only the *control flow*
differs.
"""

from __future__ import annotations

from .agent_loop import run_agent_loop
from .edgar import EdgarClient
from .llm import LLM
from .pipeline import PipelineRunner
from .profile import Memory
from .schema import Answer
from .skills import Skill, describe_skills, load_skills
from .verifier import sanitize_summary, verify


class Analyst:
    def __init__(
        self,
        client: EdgarClient | None = None,
        memory: Memory | None = None,
        llm: LLM | None = None,
        skills: dict[str, Skill] | None = None,
        memory_dir: str = "data/memory",
        use_llm_intent: bool = True,
        mode: str = "pipeline",
    ) -> None:
        self.client = client or EdgarClient()
        self.memory = memory or Memory(memory_dir)
        self.llm = llm
        self.skills = skills if skills is not None else load_skills()
        self.mode = mode  # "pipeline" | "agent"
        self.pipeline = PipelineRunner(
            self.client, self.memory, self.llm, self.skills, use_llm_intent
        )

    @property
    def last_intent(self):
        return self.pipeline.last_intent

    def run(self, query: str, history: list[dict] | None = None) -> Answer:
        if self.mode == "agent" and self.llm is not None:
            return self._run_agentic(query, history=history)
        return self.pipeline.run(query)

    def _run_agentic(self, query: str, history: list[dict] | None = None) -> Answer:
        """Agent mode: the LLM drives tool calls; the verifier still gates the answer."""
        summary_text, facts, citations = run_agent_loop(
            self.llm, self.client, query, hints=self._agent_hints(query), history=history
        )

        answer = Answer(summary=summary_text, facts=facts, citations=citations)
        issues = verify(answer)
        if issues:
            answer.summary = sanitize_summary(summary_text, facts)
            answer.summary += (
                "\n\n[verifier] flagged unsupported numeric claims "
                "(shown as [unverified]):\n"
                + "\n".join(f"  - {i}" for i in issues)
            )

        # Remember from the facts actually fetched (no explicit intent here).
        tickers = sorted({f.provenance.ticker for f in facts})
        metrics = sorted({f.metric for f in facts})
        self.memory.add_tickers(tickers)
        for mk in metrics:
            self.memory.bump_metric(mk)
        self.memory.record_query(query, tickers, metrics)
        self.memory.save()
        return answer

    def _agent_hints(self, query: str) -> list[str]:
        """Extra system-prompt lines: the sector skills + remembered corrections."""
        hints: list[str] = []
        skills_desc = describe_skills(self.skills)
        if skills_desc:
            hints.append(
                "Available sector analysis recipes — infer each company's sector "
                "yourself and use the matching recipe's metrics:\n" + skills_desc
            )
        corrections = self.memory.recent_corrections()
        if corrections:
            hints.append(
                "The user has previously requested: " + "; ".join(corrections)
                + ". Respect these preferences."
            )
        return hints
