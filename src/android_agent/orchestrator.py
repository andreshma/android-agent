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
    def __init__(self, llm: LLM, bridge: Bridge) -> None:
        self.llm = llm
        self.bridge = bridge
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
        facts = self.inspect.gather_facts(device)
        facts.update(self._caps[mission].gather_facts(device))
        return self.llm.propose_plan(mission=mission, request=request, device_facts=facts)

    def run(self, device: Device, plan: Plan):
        """Phase 2: execute an already-confirmed plan. The CLI must have
        obtained confirmation (and the extra HIGH-risk yes) before calling."""
        return self._caps[plan.mission].execute_plan(device, plan)
