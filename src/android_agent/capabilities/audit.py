"""Audit mission — read-only.

Surfaces what's on the device and what it can reach: installed packages,
which apps hold sensitive permissions (mic, camera, location), bloatware, and
notable system properties. Produces facts the LLM turns into a human report.
Nothing here changes the device.
"""

from __future__ import annotations

from ..models import Device
from .base import Capability


class AuditCapability(Capability):
    mission = "audit"

    def gather_facts(self, device: Device) -> dict:
        packages = self.bridge.execute(
            ["adb", "-s", device.serial, "shell", "pm", "list", "packages"]
        )
        # TODO(contributors): enrich with per-app permission scan via
        # `dumpsys package <pkg>` and flag mic/camera/location grants.
        return {
            "packages_raw": packages.stdout,
            "notes": "permission enrichment is a stub — see TODO",
        }
