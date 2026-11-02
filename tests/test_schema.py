"""The LLM-output -> Plan parsing is shared by both backends, so test it once."""

import json

from android_agent.llm import schema
from android_agent.models import Mission, RiskLevel

PAYLOAD = {
    "summary": "Disable two pre-installed apps you don't use.",
    "steps": [
        {
            "capability": "optimize",
            "human": "Disable the news app",
            "command": ["adb", "shell", "pm", "disable-user", "com.x.news"],
            "risk": "low",
            "reversible": True,
            "undo": ["adb", "shell", "pm", "enable", "com.x.news"],
        }
    ],
}


def test_plan_from_payload():
    plan = schema.plan_from_payload(PAYLOAD, Mission.OPTIMIZE)
    assert plan.mission is Mission.OPTIMIZE
    assert plan.steps[0].risk is RiskLevel.LOW
    assert plan.max_risk is RiskLevel.LOW


def test_plan_from_text_tolerates_code_fence():
    text = "```json\n" + json.dumps(PAYLOAD) + "\n```"
    plan = schema.plan_from_text(text, Mission.OPTIMIZE)
    assert plan.steps[0].command[-1] == "com.x.news"


def test_high_risk_detected():
    payload = {
        "summary": "Unlock the bootloader.",
        "steps": [
            {
                "capability": "unlock",
                "human": "Unlock bootloader (erases data)",
                "command": ["fastboot", "flashing", "unlock"],
                "risk": "high",
                "reversible": False,
            }
        ],
    }
    plan = schema.plan_from_payload(payload, Mission.UNLOCK)
    assert plan.max_risk is RiskLevel.HIGH
