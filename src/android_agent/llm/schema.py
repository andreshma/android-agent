"""Shared structured-output contract for turning an LLM response into a Plan.

Both backends ask the model for the SAME JSON shape and parse it here, so the
prompt contract lives in one place and the allowlist still gets the final say
when the plan runs.
"""

from __future__ import annotations

import json

from ..models import Mission, Plan

# JSON Schema for the model's structured output (used directly as the
# Anthropic tool input_schema, and described to Ollama via the prompt).
PLAN_SCHEMA: dict = {
    "type": "object",
    "required": ["summary", "steps"],
    "properties": {
        "summary": {
            "type": "string",
            "description": "One short paragraph, plain language, explaining the plan.",
        },
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["capability", "human", "command", "risk", "reversible"],
                "properties": {
                    "capability": {"type": "string"},
                    "human": {
                        "type": "string",
                        "description": "Plain-language description of this one step.",
                    },
                    "command": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "argv for adb/fastboot WITHOUT a '-s <serial>' selector; "
                            "the agent injects the target device itself."
                        ),
                    },
                    "risk": {"type": "string", "enum": ["none", "low", "high"]},
                    "reversible": {"type": "boolean"},
                    "undo": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}

PLAN_JSON_INSTRUCTIONS = (
    "Respond with ONLY a JSON object matching this schema (no prose, no code "
    "fence):\n" + json.dumps(PLAN_SCHEMA, indent=2)
)


def build_user_prompt(mission: Mission, request: str, device_facts: dict) -> str:
    return (
        f"Mission: {mission.value}\n"
        f"Operator request: {request}\n\n"
        f"Read-only device facts:\n{json.dumps(device_facts, indent=2)}\n\n"
        f"{PLAN_JSON_INSTRUCTIONS}"
    )


def _extract_json(text: str) -> dict:
    """Best-effort: find the first JSON object in the text."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{") :]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object found in model response: {text[:200]!r}")
    return json.loads(text[start : end + 1])


def plan_from_payload(payload: dict, mission: Mission) -> Plan:
    """Validate a payload dict (already parsed) into a Plan."""
    data = {"mission": mission.value, **payload}
    return Plan.model_validate(data)


def plan_from_text(text: str, mission: Mission) -> Plan:
    """Parse raw model text (JSON) into a validated Plan."""
    return plan_from_payload(_extract_json(text), mission)
