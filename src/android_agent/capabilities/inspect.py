"""Inspect — shared read-only helpers used across missions.

Not a mission of its own, but the common read-only facts (model, Android
version, bootloader state) that every mission wants before proposing a plan.
"""

from __future__ import annotations

from ..models import Device, DeviceMode
from .base import Capability


class InspectCapability(Capability):
    mission = "inspect"

    def gather_facts(self, device: Device) -> dict:
        # The serial is deliberately NOT included: the model doesn't need it (the
        # bridge injects the authorized serial itself), so there's no reason to
        # send it to a hosted backend (audit L2).
        facts: dict = {"mode": device.mode.value}
        if device.mode is DeviceMode.ADB:
            facts["model"] = self.bridge.read_property(device, "ro.product.model")
            facts["android"] = self.bridge.read_property(device, "ro.build.version.release")
        return facts
