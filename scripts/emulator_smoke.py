#!/usr/bin/env python3
"""CI smoke test: prove the CLI talks to a real adb device (the emulator).

Runs on an Android emulator in CI (see the ``emulator-smoke`` job in
``.github/workflows/ci.yml``). It is deliberately **read-only**: it only lists
devices, which exercises the real path the fake-bridge unit tests cannot —
``adb devices`` output flowing through the bridge, the parser and the allowlist.
Nothing on the device is changed.
"""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
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


if __name__ == "__main__":
    raise SystemExit(main())
