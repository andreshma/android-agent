"""Orchestrator — ties the LLM, capabilities and bridge together.

The flow for any mission is always the same two-phase contract:

    gather facts (read-only)
        -> LLM proposes a Plan
            -> show plain-language summary (+ optional drill-down to commands)
                -> operator confirms (HIGH risk requires an explicit extra yes)
                    -> capability executes the plan through the allowlisted bridge

The orchestrator itself never executes commands or asks for input — the CLI
owns the interaction. This keeps the core testable and lets a future UI reuse
it unchanged.
"""

from __future__ import annotations

from .audit_log import ActionLog
from .bridge import allowlist
from .bridge.device import Bridge
from .capabilities import bloatware
from .capabilities.audit import AuditCapability
from .capabilities.base import Capability
from .capabilities.flash import FlashCapability
from .capabilities.inspect import InspectCapability
from .capabilities.optimize import OptimizeCapability
from .capabilities.unlock import UnlockCapability
from .llm.base import LLM
from .models import Device, DeviceMode, Mission, Plan, RiskLevel

_RISK_ORDER = [RiskLevel.NONE, RiskLevel.LOW, RiskLevel.HIGH]

# Which allowlist keys each mission may use. A proposed plan whose step falls
# outside its mission's set is rejected — so e.g. an `audit` plan can never
# carry a `fastboot flash` step, independent of the mode guard.
_READONLY_ADB = {
    "adb:devices",
    "adb:get-state",
    "adb:shell:getprop",
    "adb:shell:pm list packages",
    "adb:shell:dumpsys package",
    "adb:shell:dumpsys batterystats",
    "adb:shell:cmd package list packages",
}
MISSION_KEYS: dict[Mission, set[str]] = {
    Mission.AUDIT: _READONLY_ADB,
    Mission.OPTIMIZE: _READONLY_ADB
    | {"adb:shell:pm disable-user", "adb:shell:pm enable", "adb:shell:pm clear"},
    Mission.FLASH: {"fastboot:devices", "fastboot:getvar", "fastboot:flash", "fastboot:reboot"},
    Mission.UNLOCK: {
        "fastboot:devices",
        "fastboot:getvar",
        "fastboot:flashing unlock",
        "fastboot:flashing lock",
        "fastboot:reboot",
    },
}

# pm verbs that act on a package the operator might not mean to touch.
_PM_PACKAGE_KEYS = {
    "adb:shell:pm disable-user",
    "adb:shell:pm clear",
    "adb:shell:pm enable",
}

# Which connection mode each mission requires. audit/optimize talk to a booted
# device over adb; flash/unlock need the bootloader (fastboot).
REQUIRED_MODE: dict[Mission, DeviceMode] = {
    Mission.AUDIT: DeviceMode.ADB,
    Mission.OPTIMIZE: DeviceMode.ADB,
    Mission.FLASH: DeviceMode.FASTBOOT,
    Mission.UNLOCK: DeviceMode.FASTBOOT,
}


class DeviceModeError(RuntimeError):
    """Raised when the device isn't in the mode a mission requires."""


def require_mode(device: Device, mission: Mission) -> None:
    """Guard: the device must be in the mode the mission needs."""
    needed = REQUIRED_MODE[mission]
    if device.mode is not needed:
        raise DeviceModeError(
            f"The '{mission.value}' mission needs the device in {needed.value} mode, "
            f"but {device.serial} is in {device.mode.value} mode. "
            + (
                "Enable USB debugging and boot normally."
                if needed is DeviceMode.ADB
                else "Reboot to the bootloader (e.g. `adb reboot bootloader`)."
            )
        )


class PlanRejected(RuntimeError):
    """Raised when a proposed plan is out of scope for its mission."""


def annotate_plan_risk(plan: Plan) -> None:
    """Validate and clamp a proposed plan before the user can confirm it.

    For every step: (1) validate the command against the allowlist (raises
    ``CommandDenied`` on anything not permitted), (2) reject it if the command
    is outside the mission's allowed set, (3) reject a pm action that targets a
    protected/core package, and (4) raise each step's risk to the authoritative
    level derived from the command (never downgrades)."""
    allowed = MISSION_KEYS.get(plan.mission, set())
    for step in plan.steps:
        key = allowlist.validate(step.command)  # raises if not allowlisted
        if key not in allowed:
            raise PlanRejected(
                f"step '{' '.join(step.command)}' ({key}) is not allowed for the "
                f"'{plan.mission.value}' mission"
            )
        if key in _PM_PACKAGE_KEYS and step.command and bloatware.is_protected(step.command[-1]):
            raise PlanRejected(
                f"refusing to {key.split(':')[-1]} a protected/core package: {step.command[-1]}"
            )
        derived = allowlist.risk_for(step.command)
        if _RISK_ORDER.index(derived) > _RISK_ORDER.index(step.risk):
            step.risk = derived


class Orchestrator:
    def __init__(self, llm: LLM | None, bridge: Bridge, log: ActionLog | None = None) -> None:
        # ``llm`` may be None for deterministic plans (e.g. debloat, ROM flash)
        # that don't need a model; only ``propose`` requires one.
        self.llm = llm
        self.bridge = bridge
        self.log = log
        self._caps: dict[Mission, Capability] = {
            Mission.AUDIT: AuditCapability(bridge),
            Mission.OPTIMIZE: OptimizeCapability(bridge),
            Mission.FLASH: FlashCapability(bridge),
            Mission.UNLOCK: UnlockCapability(bridge),
        }
        self.inspect = InspectCapability(bridge)

    def capability(self, mission: Mission) -> Capability:
        return self._caps[mission]

    def propose(self, device: Device, mission: Mission, request: str) -> Plan:
        """Phase 1: gather read-only facts and ask the LLM for a plan.

        The plan is validated against the allowlist and its risk levels are
        re-derived from the commands, so a hallucinated or injected plan can
        neither smuggle a non-allowlisted command past the user nor understate
        how dangerous a step is."""
        if self.llm is None:
            raise RuntimeError("propose() needs an LLM backend; none was configured.")
        require_mode(device, mission)
        facts = self.inspect.gather_facts(device)
        facts.update(self._caps[mission].gather_facts(device))
        plan = self.llm.propose_plan(mission=mission, request=request, device_facts=facts)
        annotate_plan_risk(plan)
        if self.log:
            self.log.plan_proposed(device.serial, plan)
        return plan

    def run(self, device: Device, plan: Plan):
        """Phase 2: execute an already-confirmed plan. The CLI must have
        obtained confirmation (and the extra HIGH-risk yes) before calling.

        Each step is executed and logged one at a time so the action log
        reflects exactly what ran, even if a later step fails."""
        cap = self._caps[plan.mission]
        results = []
        for step in plan.steps:
            result = cap.execute_step(device, step)
            if self.log:
                self.log.step_executed(device.serial, result)
            results.append(result)
            # Stop the sequence if a state-changing step fails — continuing a
            # half-done flash (or any LOW/HIGH step) risks bricking the device.
            # Remaining steps are reported as skipped by the caller.
            if not result.ok and step.risk is not RiskLevel.NONE:
                break
        return results
