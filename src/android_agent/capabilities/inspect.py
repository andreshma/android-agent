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
        facts: dict = {"serial": device.serial, "mode": device.mode.value}
        if device.mode is DeviceMode.ADB:
            facts["model"] = self.bridge.read_property(device, "ro.product.model")
            facts["android"] = self.bridge.read_property(device, "ro.build.version.release")
        return facts
