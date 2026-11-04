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
    """Force every action onto the one authorized device.

    Any ``-s <value>`` the caller/LLM supplied is STRIPPED and replaced with the
    authorized serial, so a plan can never target another connected device. The
    ``devices`` sub-command takes no selector and is left alone."""
    if not command or command[0] not in {"adb", "fastboot"}:
        return command
    tool, rest = command[0], command[1:]
    # Drop a leading selector if present.
    if len(rest) >= 2 and rest[0] == "-s":
        rest = rest[2:]
    if rest and rest[0] == "devices":
        return [tool, *rest]
    return [tool, "-s", serial, *rest]


# Per-key execution timeouts (seconds). ``None`` means no timeout — killing a
# partition write mid-flight can brick the device, so flashing is never timed
# out. Anything not listed uses the default.
_AUTO = object()
_DEFAULT_TIMEOUT = 120.0
_TIMEOUTS: dict[str, float | None] = {
    "fastboot:flash": None,
    "fastboot:flashing unlock": None,
    "fastboot:flashing lock": None,
}


class Bridge:
    def __init__(self, runner: Runner) -> None:
        self._runner = runner

    def execute(self, command: list[str], timeout=_AUTO) -> RunOutput:
        """Validate against the allowlist, then run. Raises CommandDenied if the
        command isn't permitted. With the default (``_AUTO``) timeout, a per-key
        timeout is used so destructive, slow operations aren't killed mid-write."""
        key = allowlist.validate(command)  # raises on anything not permitted
        effective = _TIMEOUTS.get(key, _DEFAULT_TIMEOUT) if timeout is _AUTO else timeout
        return self._runner.run(command, timeout=effective)

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
