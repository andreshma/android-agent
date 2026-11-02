"""Core data models shared across layers.

These describe the *plan/confirm/execute* contract between the orchestrator,
the capabilities and the device bridge. The LLM never speaks raw shell — it
emits a ``Plan`` made of ``Step`` objects, each one bound to a capability that
knows how to run it against the allowlisted bridge.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """How dangerous a step is, surfaced to the user before confirmation."""

    NONE = "none"          # read-only, nothing changes on the device
    LOW = "low"            # reversible (e.g. disable a package, clear cache)
    HIGH = "high"          # destructive / hard to undo (flash, wipe, unlock)


class Mission(str, Enum):
    """The four things the agent helps with, all on the user's own device."""

    AUDIT = "audit"
    OPTIMIZE = "optimize"
    FLASH = "flash"
    UNLOCK = "unlock"


class DeviceMode(str, Enum):
    ADB = "adb"            # booted into Android, debugging enabled
    FASTBOOT = "fastboot"  # bootloader mode


class Device(BaseModel):
    """A single connected device the agent is authorized to operate on."""

    serial: str
    mode: DeviceMode
    model: str | None = None
    product: str | None = None
    android_version: str | None = None
    bootloader_unlocked: bool | None = None
    # Set once the ownership/consent gate has passed for this serial.
    authorized: bool = False


class Step(BaseModel):
    """One concrete action inside a plan.

    ``human`` is the plain-language description shown by default; ``command``
    is the raw bridge invocation revealed only on drill-down. ``command`` is a
    list (argv), never a shell string, so nothing is ever word-split or
    interpreted by a shell.
    """

    capability: str                       # which capability executes this
    human: str                            # "Disable the pre-installed news app"
    command: list[str]                    # ["pm", "disable-user", "com.x.news"]
    risk: RiskLevel = RiskLevel.NONE
    reversible: bool = True
    undo: list[str] | None = None         # command to reverse a LOW-risk step


class Plan(BaseModel):
    """What the agent proposes to do, before anything runs."""

    mission: Mission
    summary: str                          # one-paragraph human explanation
    steps: list[Step] = Field(default_factory=list)

    @property
    def max_risk(self) -> RiskLevel:
        order = [RiskLevel.NONE, RiskLevel.LOW, RiskLevel.HIGH]
        return max((s.risk for s in self.steps), key=order.index, default=RiskLevel.NONE)


class StepResult(BaseModel):
    step: Step
    ok: bool
    output: str = ""
    error: str = ""
