"""Pure parsers for adb/fastboot output.

Kept free of any I/O so they can be unit-tested on any OS. The bridge calls
these on the captured stdout/stderr of real commands.
"""

from __future__ import annotations

from ..models import Device, DeviceMode


def parse_adb_devices(stdout: str) -> list[Device]:
    """Parse the output of ``adb devices -l``.

    Example line::

        ABCD1234   device usb:1-1 product:redfin model:Pixel_5 device:redfin

    Only devices in the ``device`` state (fully online) are returned; entries
    that are ``offline``, ``unauthorized`` or in recovery are skipped.
    """
    devices: list[Device] = []
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line or line.lower().startswith("list of devices"):
            continue
        parts = line.split()
        if len(parts) < 2 or parts[1] != "device":
            continue
        serial = parts[0]
        fields = dict(tok.split(":", 1) for tok in parts[2:] if ":" in tok)
        devices.append(
            Device(
                serial=serial,
                mode=DeviceMode.ADB,
                model=fields.get("model"),
                product=fields.get("product"),
            )
        )
    return devices


def parse_fastboot_devices(stdout: str) -> list[Device]:
    """Parse the output of ``fastboot devices``.

    Example line (tab- or space-separated)::

        ABCD1234    fastboot
    """
    devices: list[Device] = []
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        serial = parts[0]
        devices.append(Device(serial=serial, mode=DeviceMode.FASTBOOT))
    return devices


def parse_getvar(stderr_or_stdout: str, var: str) -> str | None:
    """fastboot prints ``getvar`` results on stderr as ``<var>: <value>``."""
    for raw in stderr_or_stdout.splitlines():
        line = raw.strip()
        # fastboot commonly prefixes informational lines with "(bootloader) ".
        if line.startswith("(bootloader)"):
            line = line[len("(bootloader)") :].strip()
        if line.startswith(f"{var}:"):
            return line.split(":", 1)[1].strip()
    return None
