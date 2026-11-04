"""Optimize mission — low risk, reversible.

Disables bloatware (without uninstalling), clears caches, and reviews
battery/startup offenders. Every step carries an ``undo`` so the operator can
roll back. Nothing is removed permanently.
"""

from __future__ import annotations

from ..models import Device, Mission, Plan, RiskLevel, Step
from . import battery, bloatware, permissions
from .base import Capability


class OptimizeCapability(Capability):
    mission = "optimize"

    def gather_facts(self, device: Device) -> dict:
        installed = self.bridge.execute(
            ["adb", "-s", device.serial, "shell", "pm", "list", "packages"]
        )
        disabled = self.bridge.execute(
            ["adb", "-s", device.serial, "shell", "pm", "list", "packages", "-d"]
        )
        installed_pkgs = permissions.parse_package_list(installed.stdout)
        candidates = bloatware.detect_bloatware(installed_pkgs)
        return {
            "installed_count": len(installed_pkgs),
            "disabled_packages": permissions.parse_package_list(disabled.stdout),
            "bloatware_candidates": candidates,
            "battery_top_consumers": self.battery_top_consumers(device),
        }

    def battery_top_consumers(self, device: Device, limit: int = 10) -> list[dict]:
        """Read-only: the apps estimated to drain the most battery."""
        stats = self.bridge.execute(
            ["adb", "-s", device.serial, "shell", "dumpsys", "batterystats"]
        )
        uids = self.bridge.execute(
            ["adb", "-s", device.serial, "shell", "cmd", "package", "list", "packages", "-U"]
        )
        return battery.top_power_consumers(
            stats.stdout, battery.parse_uid_map(uids.stdout), limit=limit
        )

    @staticmethod
    def disable_package_step(serial: str, package: str, reason: str = "") -> Step:
        """Build a reversible step to disable a package for the current user."""
        why = f" — {reason}" if reason else ""
        return Step(
            capability="optimize",
            human=f"Disable '{package}'{why}. It stays installed and can be re-enabled.",
            command=["adb", "-s", serial, "shell", "pm", "disable-user", package],
            risk=RiskLevel.LOW,
            reversible=True,
            undo=["adb", "-s", serial, "shell", "pm", "enable", package],
        )

    def build_debloat_plan(self, device: Device) -> Plan:
        """A deterministic plan (no LLM) that disables the detected bloatware.

        Each step is reversible; the operator still confirms before it runs.
        """
        facts = self.gather_facts(device)
        candidates: dict[str, str] = facts["bloatware_candidates"]
        steps = [
            self.disable_package_step(device.serial, pkg, reason)
            for pkg, reason in sorted(candidates.items())
        ]
        summary = (
            f"Disable {len(steps)} likely-bloatware app(s) found on the device. "
            "All changes are reversible (the apps stay installed and can be "
            "re-enabled)."
            if steps
            else "No likely-bloatware apps were detected. Nothing to do."
        )
        return Plan(mission=Mission.OPTIMIZE, summary=summary, steps=steps)
