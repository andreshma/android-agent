"""Unlock mission — HIGH risk, operator's own device only.

Unlocks the bootloader of the operator's own device via
``fastboot flashing unlock``. This is a legitimate, user-initiated operation
(it is what enables installing a custom ROM), but it ERASES ALL DATA and the
device itself shows an on-screen confirmation the operator must accept.

Scope boundary (enforced by the consent gate, restated here):
  • This unlocks a device the operator owns and has connected.
  • It does NOT bypass a lock screen, a Google/FRP account, or carrier locks,
    and it does NOT work on a device whose owner hasn't enabled OEM unlocking.
    Those are out of scope by design.
"""

from __future__ import annotations

from ..models import Device, DeviceMode, RiskLevel, Step
from .base import Capability


class UnlockCapability(Capability):
    mission = "unlock"

    def gather_facts(self, device: Device) -> dict:
        if device.mode is not DeviceMode.FASTBOOT:
            return {"error": "device must be in fastboot mode to read unlock state"}
        state = self.bridge.execute(["fastboot", "-s", device.serial, "getvar", "unlocked"])
        return {"unlocked_raw": state.stderr or state.stdout}

    @staticmethod
    def unlock_step(serial: str) -> Step:
        return Step(
            capability="unlock",
            human=(
                "Unlock the bootloader of your own device. This ERASES ALL DATA "
                "and the phone will ask you to confirm on its screen. Only continue "
                "if this is your device and you have a backup."
            ),
            command=["fastboot", "-s", serial, "flashing", "unlock"],
            risk=RiskLevel.HIGH,
            reversible=False,
        )
