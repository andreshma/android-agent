"""Device bridge — the single doorway to adb/fastboot.

Everything that touches a real device goes through ``Bridge``: it validates
each command against the allowlist, then hands it to the chosen sandbox runner.
No other layer is allowed to call subprocess directly.
"""

from __future__ import annotations

from ..models import Device, DeviceMode
from . import allowlist, parse
from .sandbox import Runner, RunOutput


def with_serial(command: list[str], serial: str) -> list[str]:
    """Insert ``-s <serial>`` after the tool so every action targets the one
    authorized device — regardless of what the LLM proposed. Not added to the
    ``devices`` sub-command, which takes no selector."""
    if not command or command[0] not in {"adb", "fastboot"}:
        return command
    if "-s" in command:
        return command
    rest = command[1:]
    if rest and rest[0] == "devices":
        return command
    return [command[0], "-s", serial, *rest]


class Bridge:
    def __init__(self, runner: Runner) -> None:
        self._runner = runner

    def execute(self, command: list[str], timeout: float = 120.0) -> RunOutput:
        """Validate against the allowlist, then run. Raises CommandDenied if
        the command isn't explicitly permitted."""
        allowlist.validate(command)  # raises on anything not permitted
        return self._runner.run(command, timeout=timeout)

    # --- discovery -------------------------------------------------------
    def list_devices(self) -> list[Device]:
        """Detect connected devices in both adb and fastboot modes."""
        devices: list[Device] = []
        adb_out = self.execute(["adb", "devices", "-l"])
        if adb_out.ok:
            devices.extend(parse.parse_adb_devices(adb_out.stdout))
        fb_out = self.execute(["fastboot", "devices"])
        if fb_out.ok:
            devices.extend(parse.parse_fastboot_devices(fb_out.stdout))
        return devices

    def find_device(self, serial: str) -> Device | None:
        for d in self.list_devices():
            if d.serial == serial:
                return d
        return None

    def read_property(self, device: Device, prop: str) -> str:
        """Example read-only helper used by audit/inspect."""
        if device.mode is not DeviceMode.ADB:
            raise ValueError("getprop requires the device in adb mode")
        out = self.execute(["adb", "-s", device.serial, "shell", "getprop", prop])
        return out.stdout.strip()
