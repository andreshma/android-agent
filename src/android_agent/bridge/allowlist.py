"""Command allowlist — the core security boundary.

The LLM proposes steps, but it can NEVER cause an arbitrary shell command to
run. Every ``Step.command`` is validated here against a per-tool allowlist
before the bridge will execute it. The first token selects the tool (adb /
fastboot) and the second the sub-command, which must appear in the set below.

Rules:
  • commands are argv lists, never shell strings (no word-splitting, no `;`)
  • the sub-command must be explicitly allowed
  • a small set of sub-commands is HIGH risk and gated separately upstream

Adding a capability means adding its sub-commands here on purpose — that is the
point. A denied command is a bug or an attack, never something to "work around"
by shelling out directly.
"""

from __future__ import annotations

# adb sub-commands the agent is allowed to run. Grouped by the mission that
# needs them so the boundary stays readable.
_ADB_ALLOWED: dict[str, str] = {
    # --- inspect / audit (read-only) ---
    "devices": "list connected devices",
    "get-state": "device connection state",
    "shell:getprop": "read a system property",
    "shell:pm list packages": "list installed packages",
    "shell:dumpsys": "read a system service's state",
    "shell:cmd package": "query package info",
    # --- optimize (reversible) ---
    "shell:pm disable-user": "disable (not remove) a package for the user",
    "shell:pm enable": "re-enable a previously disabled package",
    "shell:pm clear": "clear an app's cache/data",
    # --- backup before anything risky ---
    "backup": "create a device backup",
}

# fastboot sub-commands. Everything here is HIGH risk by nature.
_FASTBOOT_ALLOWED: dict[str, str] = {
    "devices": "list devices in bootloader mode",
    "getvar": "read a bootloader variable (e.g. unlocked state)",
    "flashing unlock": "unlock the bootloader of your own device (ERASES DATA)",
    "flashing lock": "re-lock the bootloader",
    "flash": "write an image to a partition",
    "reboot": "reboot the device",
}

_TOOLS = {"adb": _ADB_ALLOWED, "fastboot": _FASTBOOT_ALLOWED}

# Authoritative risk per allowlist key (``validate`` returns ``tool:key``).
# This is the source of truth for how dangerous a command is — the LLM's
# self-declared risk is never trusted over this. Anything not listed is treated
# as HIGH (fail-safe), though ``validate`` denies unknown commands first.
from ..models import RiskLevel  # noqa: E402  (kept near the data it annotates)

_RISK: dict[str, RiskLevel] = {
    "adb:devices": RiskLevel.NONE,
    "adb:get-state": RiskLevel.NONE,
    "adb:shell:getprop": RiskLevel.NONE,
    "adb:shell:pm list packages": RiskLevel.NONE,
    "adb:shell:dumpsys": RiskLevel.NONE,
    "adb:shell:cmd package": RiskLevel.NONE,
    "adb:shell:pm disable-user": RiskLevel.LOW,
    "adb:shell:pm enable": RiskLevel.LOW,
    "adb:shell:pm clear": RiskLevel.LOW,
    "adb:backup": RiskLevel.LOW,
    "fastboot:devices": RiskLevel.NONE,
    "fastboot:getvar": RiskLevel.NONE,
    "fastboot:reboot": RiskLevel.LOW,
    "fastboot:flashing unlock": RiskLevel.HIGH,
    "fastboot:flashing lock": RiskLevel.HIGH,
    "fastboot:flash": RiskLevel.HIGH,
}


class CommandDenied(RuntimeError):
    """Raised when a proposed command is not on the allowlist."""


def _match_key(tool: str, argv: list[str]) -> str | None:
    """Find the longest allowlist key that prefixes this argv.

    Lets us allow a specific ``shell pm disable-user`` while still denying an
    arbitrary ``shell`` command.
    """
    allowed = _TOOLS.get(tool, {})
    # Build candidate keys from progressively longer argv prefixes, joining
    # the `shell` sub-command with ':' to match the allowlist spelling.
    rest = argv[1:]
    # Skip a leading device selector (`-s <serial>`), which both adb and
    # fastboot accept before the real sub-command.
    if len(rest) >= 2 and rest[0] == "-s":
        rest = rest[2:]
    if rest and rest[0] == "shell":
        prefix = "shell:" + " ".join(rest[1:])
    else:
        prefix = " ".join(rest)
    for key in sorted(allowed, key=len, reverse=True):
        if prefix == key or prefix.startswith(key + " "):
            return key
    return None


def validate(command: list[str]) -> str:
    """Validate an argv command. Returns the matched allowlist key or raises.

    The returned key is what callers use to decide HIGH-risk gating.
    """
    if not command:
        raise CommandDenied("empty command")
    tool = command[0]
    if tool not in _TOOLS:
        raise CommandDenied(f"tool {tool!r} is not allowed (only: {', '.join(_TOOLS)})")
    if any(";" in tok or "&&" in tok or "|" in tok for tok in command):
        raise CommandDenied("shell metacharacters are not allowed in a command")
    key = _match_key(tool, command)
    if key is None:
        raise CommandDenied(
            f"{tool} sub-command not on allowlist: {' '.join(command[1:]) or '(none)'}"
        )
    return f"{tool}:{key}"


def risk_for(command: list[str]) -> RiskLevel:
    """Authoritative risk for a command, derived from the allowlist.

    Validates first (raising ``CommandDenied`` if not permitted), then returns
    the mapped risk. An allowlisted-but-unmapped command defaults to HIGH so a
    new entry is never silently treated as safe.
    """
    full_key = validate(command)
    return _RISK.get(full_key, RiskLevel.HIGH)
