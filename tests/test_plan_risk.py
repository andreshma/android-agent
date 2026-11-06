"""Risk is derived from the allowlist, not trusted from the LLM."""

import pytest

from android_agent.bridge import allowlist
from android_agent.bridge.allowlist import CommandDenied
from android_agent.models import Mission, Plan, RiskLevel, Step
from android_agent.orchestrator import PlanRejected, annotate_plan_risk


def test_risk_for_derives_from_command():
    assert allowlist.risk_for(["adb", "shell", "getprop", "ro.x"]) is RiskLevel.NONE
    assert allowlist.risk_for(["adb", "shell", "pm", "disable-user", "p"]) is RiskLevel.LOW
    assert allowlist.risk_for(["fastboot", "flashing", "unlock"]) is RiskLevel.HIGH


def test_pm_clear_is_high_risk_not_low():
    # `pm clear` wipes app data; it must not be presented as a LOW/reversible
    # tidy-up (audit M1).
    assert allowlist.risk_for(["adb", "shell", "pm", "clear", "com.x"]) is RiskLevel.HIGH


def test_reversible_is_derived_not_trusted():
    # Only disable/enable (and read-only commands) are reversible; pm clear,
    # flash and unlock are not — regardless of what the LLM claims (audit M1).
    assert allowlist.reversible_for(["adb", "shell", "pm", "disable-user", "p"]) is True
    assert allowlist.reversible_for(["adb", "shell", "pm", "enable", "p"]) is True
    assert allowlist.reversible_for(["adb", "shell", "getprop", "ro.x"]) is True
    assert allowlist.reversible_for(["adb", "shell", "pm", "clear", "com.x"]) is False
    assert allowlist.reversible_for(["fastboot", "flashing", "unlock"]) is False


def test_validate_plan_overrides_lying_reversible_flag():
    # The LLM marks a data wipe reversible with a bogus undo; validate_plan
    # must correct both (audit M1/M2).
    plan = Plan(
        mission=Mission.OPTIMIZE,
        summary="…",
        steps=[
            Step(
                capability="optimize",
                human="harmless tidy-up",
                command=["adb", "shell", "pm", "clear", "com.x"],
                risk=RiskLevel.LOW,
                reversible=True,
                undo=["adb", "shell", "echo", "nope"],
            )
        ],
    )
    annotate_plan_risk(plan)
    assert plan.steps[0].risk is RiskLevel.HIGH
    assert plan.steps[0].reversible is False
    assert plan.steps[0].undo is None


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


def test_relock_is_rejected_for_unlock_mission():
    # Re-locking the bootloader is a deliberate non-goal (can brick a device on
    # a custom ROM); no mission may propose it (audit M8).
    plan = Plan(
        mission=Mission.UNLOCK,
        summary="…",
        steps=[
            Step(
                capability="unlock",
                human="re-lock",
                command=["fastboot", "flashing", "lock"],
                risk=RiskLevel.HIGH,
            )
        ],
    )
    with pytest.raises(PlanRejected):
        annotate_plan_risk(plan)


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
