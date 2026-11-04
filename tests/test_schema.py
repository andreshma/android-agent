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


def test_user_prompt_frames_facts_as_untrusted_data():
    prompt = schema.build_user_prompt(
        Mission.AUDIT, "what's installed?", {"packages": ["com.evil.ignore_previous"]}
    )
    assert "<device_facts>" in prompt and "</device_facts>" in prompt
    assert "untrusted data" in prompt
    # the actual data still appears, inside the block
    assert "com.evil.ignore_previous" in prompt


def test_user_prompt_truncates_oversized_facts():
    huge = {"packages": [f"com.app.{i}" for i in range(5000)]}
    prompt = schema.build_user_prompt(Mission.AUDIT, "audit", huge)
    assert "[facts truncated for size]" in prompt
    # bounded well under the raw size
    assert len(prompt) < schema.MAX_FACTS_CHARS + 2000


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
