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
from .bridge.device import Bridge
from .capabilities.audit import AuditCapability
from .capabilities.base import Capability
from .capabilities.flash import FlashCapability
from .capabilities.inspect import InspectCapability
from .capabilities.optimize import OptimizeCapability
from .capabilities.unlock import UnlockCapability
from .llm.base import LLM
from .models import Device, Mission, Plan


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
        """Phase 1: gather read-only facts and ask the LLM for a plan."""
        if self.llm is None:
            raise RuntimeError("propose() needs an LLM backend; none was configured.")
        facts = self.inspect.gather_facts(device)
        facts.update(self._caps[mission].gather_facts(device))
        plan = self.llm.propose_plan(mission=mission, request=request, device_facts=facts)
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
        return results
