"""Capability base class.

A capability owns one mission. It knows how to (a) gather read-only facts about
the device for the LLM, and (b) execute the steps of an approved plan through
the bridge. Capabilities never talk to subprocess directly and never skip the
consent gate.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..bridge.device import Bridge, with_serial
from ..consent import require_authorized
from ..models import Device, Plan, RiskLevel, Step, StepResult


class Capability(ABC):
    mission: str

    def __init__(self, bridge: Bridge) -> None:
        self.bridge = bridge

    @abstractmethod
    def gather_facts(self, device: Device) -> dict:
        """Read-only snapshot handed to the LLM to reason over."""

    def execute_step(self, device: Device, step: Step) -> StepResult:
        """Run one step. Consent is enforced here for every capability, and the
        authorized device's serial is injected so the action can only ever hit
        that device."""
        require_authorized(device)
        command = with_serial(step.command, device.serial)
        out = self.bridge.execute(command)
        return StepResult(step=step, ok=out.ok, output=out.stdout, error=out.stderr)

    def execute_plan(self, device: Device, plan: Plan) -> list[StepResult]:
        require_authorized(device)
        results: list[StepResult] = []
        for step in plan.steps:
            results.append(self.execute_step(device, step))
        return results

    @staticmethod
    def has_high_risk(plan: Plan) -> bool:
        return plan.max_risk is RiskLevel.HIGH
