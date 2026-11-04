"""Regression tests for audit findings H2, H4, H5 and M4 at the orchestrator."""

import pytest

from android_agent.bridge.device import Bridge
from android_agent.bridge.sandbox import RunOutput
from android_agent.models import Device, DeviceMode, Mission, Plan, RiskLevel, Step
from android_agent.orchestrator import Orchestrator, PlanRejected, annotate_plan_risk


# --- M4: mission-scope + protected package ---------------------------------
def _step(command, risk=RiskLevel.NONE, cap="x"):
    return Step(capability=cap, human="…", command=command, risk=risk)


def test_off_mission_command_is_rejected():
    # An audit plan may not carry a fastboot flash step.
    plan = Plan(
        mission=Mission.AUDIT, summary="…", steps=[_step(["fastboot", "flash", "boot", "b.img"])]
    )
    with pytest.raises(PlanRejected):
        annotate_plan_risk(plan)


def test_protected_package_disable_is_rejected():
    plan = Plan(
        mission=Mission.OPTIMIZE,
        summary="…",
        steps=[_step(["adb", "shell", "pm", "disable-user", "com.android.systemui"])],
    )
    with pytest.raises(PlanRejected):
        annotate_plan_risk(plan)


# --- H4: stop the sequence after a failed state-changing step --------------
class _FlakyRunner:
    """ok for everything except a flash of 'system', which fails."""

    def run(self, command, timeout=None):
        if "system" in command:
            return RunOutput(1, "", "write failed")
        return RunOutput(0, "", "")


def _fastboot_device():
    return Device(serial="S1", mode=DeviceMode.FASTBOOT, authorized=True)


def test_run_stops_after_failed_flash_step():
    bridge = Bridge(_FlakyRunner())
    orch = Orchestrator(None, bridge)
    plan = Plan(
        mission=Mission.FLASH,
        summary="…",
        steps=[
            _step(["fastboot", "flash", "boot", "boot.img"], RiskLevel.HIGH, "flash"),
            _step(["fastboot", "flash", "system", "system.img"], RiskLevel.HIGH, "flash"),
            _step(["fastboot", "reboot"], RiskLevel.HIGH, "flash"),
        ],
    )
    results = orch.run(_fastboot_device(), plan)
    # boot ok, system failed -> stop; reboot never runs.
    assert len(results) == 2
    assert results[0].ok and not results[1].ok


# --- H5: flashing is never killed by the default timeout -------------------
class _TimeoutSpyRunner:
    def __init__(self):
        self.seen: list = []

    def run(self, command, timeout=None):
        self.seen.append((tuple(command), timeout))
        return RunOutput(0, "", "")


def test_flash_has_no_timeout_but_reads_do():
    spy = _TimeoutSpyRunner()
    bridge = Bridge(spy)
    bridge.execute(["fastboot", "-s", "S1", "flash", "boot", "boot.img"])
    bridge.execute(["adb", "-s", "S1", "shell", "getprop", "ro.x"])
    timeouts = {cmd: t for cmd, t in spy.seen}
    assert timeouts[("fastboot", "-s", "S1", "flash", "boot", "boot.img")] is None
    assert timeouts[("adb", "-s", "S1", "shell", "getprop", "ro.x")] == 120.0
