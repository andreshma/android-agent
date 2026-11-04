"""External LLM backend via the Claude API.

More capable reasoning for planning flashes/upgrades. Optional dependency:
install with ``pip install android-agent[anthropic]`` and set ANTHROPIC_API_KEY.

It returns a ``Plan`` through a forced ``emit_plan`` tool call whose input
schema is the shared ``schema.PLAN_SCHEMA``.
"""

from __future__ import annotations

import os

from ..models import Mission, Plan
from . import schema
from .base import LLM, SYSTEM_PROMPT

# Default to the latest capable Claude model; override via constructor.
_DEFAULT_MODEL = "claude-opus-4-8"


class AnthropicLLM(LLM):
    name = "anthropic"

    def __init__(self, model: str = _DEFAULT_MODEL, api_key: str | None = None) -> None:
        try:
            import anthropic  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "The anthropic extra is not installed. Run: pip install android-agent[anthropic]"
            ) from exc
        from anthropic import Anthropic

        self.model = model
        self._client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def _message(self, user: str) -> str:
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in msg.content if block.type == "text")

    def propose_plan(self, *, mission: Mission, request: str, device_facts: dict) -> Plan:
        # Force the model to answer through a single structured tool call whose
        # input matches the shared Plan schema.
        tool = {
            "name": "emit_plan",
            "description": "Return the proposed plan of steps for the operator to confirm.",
            "input_schema": schema.PLAN_SCHEMA,
        }
        # We build the tool/tool_choice params as plain dicts (they match the
        # SDK's TypedDicts at runtime); mypy can't see that through the dict, so
        # the overload match is suppressed here deliberately.
        msg = self._client.messages.create(  # type: ignore[call-overload]
            model=self.model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=[tool],
            tool_choice={"type": "tool", "name": "emit_plan"},
            messages=[
                {
                    "role": "user",
                    "content": schema.build_user_prompt(mission, request, device_facts),
                }
            ],
        )
        if getattr(msg, "stop_reason", None) == "max_tokens":
            raise RuntimeError(
                "the model's plan was cut off at max_tokens before completing; "
                "it may be truncated, so it is rejected rather than run partially."
            )
        for block in msg.content:
            if block.type == "tool_use" and block.name == "emit_plan":
                return schema.plan_from_payload(dict(block.input), mission)
        raise RuntimeError("model did not return an emit_plan tool call")

    def explain(self, text: str) -> str:
        return self._message(f"Explain this device output in plain language:\n\n{text}")
