"""Audit mission — read-only.

Surfaces what's on the device and what it can reach: installed packages,
which apps hold sensitive permissions (mic, camera, location), bloatware, and
notable system properties. Produces facts the LLM turns into a human report.
Nothing here changes the device.
"""

from __future__ import annotations

from ..models import Device
from . import permissions
from .base import Capability

# Cap how many apps we deep-scan for permissions in one pass, so an audit on a
# phone with hundreds of apps stays responsive. Third-party apps are scanned
# first since they're the interesting ones.
_MAX_PERMISSION_SCANS = 60


class AuditCapability(Capability):
    mission = "audit"

    def gather_facts(self, device: Device) -> dict:
        all_pkgs = self.bridge.execute(
            ["adb", "-s", device.serial, "shell", "pm", "list", "packages"]
        )
        third_party = self.bridge.execute(
            ["adb", "-s", device.serial, "shell", "pm", "list", "packages", "-3"]
        )
        third_party_pkgs = permissions.parse_package_list(third_party.stdout)
        sensitive = self.scan_sensitive_permissions(device, third_party_pkgs)
        return {
            "packages_raw": all_pkgs.stdout,
            "third_party_count": len(third_party_pkgs),
            "apps_with_sensitive_permissions": sensitive,
            "scanned": min(len(third_party_pkgs), _MAX_PERMISSION_SCANS),
        }

    def scan_sensitive_permissions(
        self, device: Device, packages: list[str]
    ) -> dict[str, list[str]]:
        """For each app, return the granted privacy-sensitive permissions.

        Only apps that actually hold at least one sensitive grant are included,
        so the LLM gets a focused list rather than every package.
        """
        result: dict[str, list[str]] = {}
        for pkg in packages[:_MAX_PERMISSION_SCANS]:
            out = self.bridge.execute(
                ["adb", "-s", device.serial, "shell", "dumpsys", "package", pkg]
            )
            if not out.ok:
                continue
            labels = permissions.sensitive_grants(out.stdout)
            if labels:
                result[pkg] = labels
        return result
