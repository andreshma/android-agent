"""Optimize mission — low risk, reversible.

Disables bloatware (without uninstalling), clears caches, and reviews
battery/startup offenders. Every step carries an ``undo`` so the operator can
roll back. Nothing is removed permanently.
"""

from __future__ import annotations

from ..models import Device, RiskLevel, Step
from .base import Capability


class OptimizeCapability(Capability):
    mission = "optimize"

    def gather_facts(self, device: Device) -> dict:
        packages = self.bridge.execute(
            ["adb", "-s", device.serial, "shell", "pm", "list", "packages", "-d"]
        )
        return {"disabled_packages_raw": packages.stdout}

    @staticmethod
    def disable_package_step(serial: str, package: str) -> Step:
        """Build a reversible step to disable a package for the current user."""
        return Step(
            capability="optimize",
            human=f"Disable the app '{package}' (it stays installed and can be re-enabled).",
            command=["adb", "-s", serial, "shell", "pm", "disable-user", package],
            risk=RiskLevel.LOW,
            reversible=True,
            undo=["adb", "-s", serial, "shell", "pm", "enable", package],
        )
