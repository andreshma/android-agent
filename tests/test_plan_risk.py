"""Risk is derived from the allowlist, not trusted from the LLM."""

import pytest

from android_agent.bridge import allowlist
from android_agent.bridge.allowlist import CommandDenied
from android_agent.models import Mission, Plan, RiskLevel, Step
from android_agent.orchestrator import annotate_plan_risk


def test_risk_for_derives_from_command():
    assert allowlist.risk_for(["adb", "shell", "getprop", "ro.x"]) is RiskLevel.NONE
    assert allowlist.risk_for(["adb", "shell", "pm", "disable-user", "p"]) is RiskLevel.LOW
    assert allowlist.risk_for(["fastboot", "flashing", "unlock"]) is RiskLevel.HIGH


def test_annotate_upgrades_understated_risk():
    # LLM claims a bootloader unlock is "low" risk — must be forced to HIGH.
    plan = Plan(
        mission=Mission.UNLOCK,
        summary="…",
        steps=[
            Step(
                capability="unlock",
                human="unlock",
                command=["fastboot", "flashing", "unlock"],
                risk=RiskLevel.LOW,
            )
        ],
    )
    annotate_plan_risk(plan)
    assert plan.steps[0].risk is RiskLevel.HIGH
    assert plan.max_risk is RiskLevel.HIGH


def test_annotate_does_not_downgrade():
    # A read-only command the LLM marked HIGH stays as the stricter value.
    plan = Plan(
        mission=Mission.AUDIT,
        summary="…",
        steps=[
            Step(
                capability="audit",
                human="list",
                command=["adb", "shell", "pm", "list", "packages"],
                risk=RiskLevel.HIGH,
            )
        ],
    )
    annotate_plan_risk(plan)
    assert plan.steps[0].risk is RiskLevel.HIGH


def test_annotate_rejects_non_allowlisted_command():
    # A smuggled arbitrary command is rejected before the user can confirm.
    plan = Plan(
        mission=Mission.AUDIT,
        summary="…",
        steps=[
            Step(
                capability="audit",
                human="innocent looking",
                command=["adb", "shell", "rm", "-rf", "/sdcard"],
                risk=RiskLevel.NONE,
            )
        ],
    )
    with pytest.raises(CommandDenied):
        annotate_plan_risk(plan)
