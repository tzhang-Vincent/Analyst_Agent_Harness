"""Minimal, provider-agnostic LLM interface.

One method, :meth:`LLM.chat`, with a single normalized message format so the
rest of the harness never cares which provider is behind it:

- ``anthropic`` (default) — Anthropic Messages API, model via ``LLM_MODEL``.
- ``openai``        — OpenAI chat completions.
- ``deepseek``      — OpenAI-compatible endpoint (``https://api.deepseek.com``).

The SDKs are imported lazily, so the deterministic data layer and eval oracle
run with no LLM dependency installed. ``LLM_BASE_URL`` lets you point any
provider at a proxy (e.g. serving ``deepseek-v4-pro`` through an
Anthropic-compatible endpoint).
"""

from __future__ import annotations

import json
import os
from typing import Any

PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic")
MODEL = os.environ.get("LLM_MODEL", "deepseek-v4-pro")
BASE_URL = os.environ.get("LLM_BASE_URL", "")


class LLMError(RuntimeError):
    pass


def is_configured(provider: str | None = None) -> bool:
    provider = provider or PROVIDER
    keys = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
    }
    return bool(os.environ.get(keys.get(provider, "")))


# --- format conversion (pure, unit-testable) -------------------------------

def to_anthropic_tools(tools: list[dict]) -> list[dict]:
    """Convert OpenAI-style tools to Anthropic ``tools`` blocks."""
    out = []
    for t in tools:
        fn = t.get("function", {})
        out.append(
            {
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object"}),
            }
        )
    return out


def parse_anthropic_response(resp: Any) -> dict:
    """Normalize an Anthropic Messages response to the internal shape."""
    content = ""
    tool_calls = []
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            content += block.text
        elif getattr(block, "type", None) == "tool_use":
            tool_calls.append(
                {
                    "id": block.id,
                    "name": block.name,
                    "arguments": dict(block.input or {}),
                }
            )
    return {"role": "assistant", "content": content or None, "tool_calls": tool_calls}


def parse_openai_response(resp: Any) -> dict:
    """Normalize an OpenAI/DeepSeek chat response to the internal shape."""
    msg = resp.choices[0].message
    tool_calls = []
    for tc in msg.tool_calls or []:
        args = tc.function.arguments
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        tool_calls.append({"id": tc.id, "name": tc.function.name, "arguments": args})
    return {"role": "assistant", "content": msg.content or None, "tool_calls": tool_calls}


class LLM:
    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.provider = provider or PROVIDER
        self.model = model or MODEL
        self.base_url = base_url or BASE_URL

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
    ) -> dict:
        """Return a normalized assistant message (``content`` + ``tool_calls``)."""
        if self.provider == "anthropic":
            return self._chat_anthropic(messages, tools, tool_choice)
        return self._chat_openai(messages, tools, tool_choice)

    # -- anthropic ---------------------------------------------------------
    def _chat_anthropic(self, messages, tools, tool_choice) -> dict:
        import anthropic

        if not is_configured("anthropic"):
            raise LLMError("ANTHROPIC_API_KEY is not set")
        client = anthropic.Anthropic(base_url=self.base_url or None)

        system = "\n".join(
            m["content"] for m in messages if m["role"] == "system"
        ) or None
        msgs = [m for m in messages if m["role"] != "system"]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": msgs,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = to_anthropic_tools(tools)
            if tool_choice:
                kwargs["tool_choice"] = {"type": "tool", "name": tool_choice}
        return parse_anthropic_response(client.messages.create(**kwargs))

    # -- openai / deepseek -------------------------------------------------
    def _chat_openai(self, messages, tools, tool_choice) -> dict:
        import openai

        kwargs: dict[str, Any] = {}
        if self.provider == "deepseek":
            if not is_configured("deepseek"):
                raise LLMError("DEEPSEEK_API_KEY is not set")
            kwargs["base_url"] = self.base_url or "https://api.deepseek.com"
            kwargs["api_key"] = os.environ["DEEPSEEK_API_KEY"]
        else:
            if not is_configured("openai"):
                raise LLMError("OPENAI_API_KEY is not set")
            if self.base_url:
                kwargs["base_url"] = self.base_url
        client = openai.OpenAI(**kwargs)

        params: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
        }
        if tools:
            params["tools"] = tools
            if tool_choice:
                params["tool_choice"] = {
                    "type": "function",
                    "function": {"name": tool_choice},
                }
        return parse_openai_response(client.chat.completions.create(**params))


def build_intent_tool() -> dict:
    """The single tool schema used to force a structured intent parse."""
    return {
        "type": "function",
        "function": {
            "name": "parse_intent",
            "description": "Parse a financial research question into structured fields.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tickers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Company tickers mentioned (e.g. NVDA, AMD).",
                    },
                    "metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Canonical metric keys: revenue, net_income, gross_profit, operating_income, rd_expense, cost_of_revenue, total_assets, total_liabilities, cash, operating_cash_flow, diluted_eps, shares_outstanding.",
                    },
                    "num_periods": {"type": "integer", "description": "Number of periods to return (default 4)."},
                    "frequency": {"type": "string", "enum": ["quarterly", "annual"], "description": "quarterly or annual."},
                },
                "required": ["tickers", "metrics"],
            },
        },
    }
