#!/usr/bin/env python3
"""CI smoke test: prove the CLI talks to a real adb device (the emulator).

Runs on an Android emulator in CI (see the ``emulator-smoke`` job in
``.github/workflows/ci.yml``). It exercises the real paths the fake-bridge unit
tests cannot cover: ``adb`` output flowing through the bridge, the parsers and
the allowlist, against a booted device. Everything here is **read-only** —
nothing on the device is changed (it lists devices and gathers the ``optimize``
mission's facts; it never disables a package).
"""

from __future__ import annotations

import subprocess
import sys


def _check_devices_cli() -> int:
    """`android-agent devices` end-to-end: bridge -> parse -> allowlist."""
    try:
        proc = subprocess.run(
            ["android-agent", "devices"],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except FileNotFoundError:
        print("FAIL: `android-agent` is not on PATH (install the package first)", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired:
        print("FAIL: `android-agent devices` timed out", file=sys.stderr)
        return 1

    output = (proc.stdout or "") + (proc.stderr or "")
    print(output)

    if proc.returncode != 0:
        print(f"FAIL: `android-agent devices` exited {proc.returncode}", file=sys.stderr)
        return 1

    # The emulator registers as `emulator-5554` (or similar) in adb mode.
    if "emulator-" not in output:
        print("FAIL: no emulator listed by `android-agent devices`", file=sys.stderr)
        return 1

    print("OK: emulator detected end-to-end via `android-agent devices`")
    return 0


def _check_optimize_read_path() -> int:
    """Exercise the ``optimize`` mission's read-only fact gathering, live.

    ``OptimizeCapability.gather_facts`` runs ``pm list packages`` (installed and
    disabled), bloatware detection, and the battery ranking
    (``dumpsys batterystats`` + ``cmd package list packages -U`` ->
    ``battery.top_power_consumers``) over the real bridge against the emulator.
    This is the live counterpart to the unit tests that parse *captured*
    ``dumpsys`` output. It is read-only: ``gather_facts`` disables nothing.
    """
    from android_agent.bridge.device import Bridge
    from android_agent.bridge.sandbox import LocalRunner
    from android_agent.capabilities.optimize import OptimizeCapability
    from android_agent.models import DeviceMode

    bridge = Bridge(LocalRunner())
    adb_devices = [d for d in bridge.list_devices() if d.mode is DeviceMode.ADB]
    if not adb_devices:
        print("FAIL: no adb-mode device for the optimize read path", file=sys.stderr)
        return 1
    device = adb_devices[0]

    try:
        facts = OptimizeCapability(bridge).gather_facts(device)
    except Exception as exc:  # a smoke must surface any live failure, not hide it
        print(f"FAIL: optimize gather_facts raised on the live device: {exc!r}", file=sys.stderr)
        return 1

    installed = facts.get("installed_count", 0)
    top = facts.get("battery_top_consumers", [])
    if not isinstance(installed, int) or installed <= 0:
        print(
            f"FAIL: expected a positive installed-package count, got {installed!r}",
            file=sys.stderr,
        )
        return 1
    if not isinstance(top, list):
        print(
            f"FAIL: battery_top_consumers should be a list, got {type(top).__name__}",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: optimize read path live on the emulator — {installed} packages, "
        f"{len(facts.get('bloatware_candidates', {}))} bloatware candidate(s), "
        f"{len(top)} battery-consumer row(s) parsed from real `dumpsys batterystats`"
    )
    return 0


def main() -> int:
    rc = _check_devices_cli()
    if rc != 0:
        return rc
    return _check_optimize_read_path()


if __name__ == "__main__":
    raise SystemExit(main())
