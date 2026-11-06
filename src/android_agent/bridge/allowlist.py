"""Command allowlist — the core security boundary.

The LLM proposes steps, but it can NEVER cause an arbitrary command to run.
Every ``Step.command`` is validated here before the bridge will execute it.
Validation has two layers:

  1. **Shape** — the first tokens must match an explicit per-tool key (so
     ``adb shell pm disable-user`` is allowed while a bare ``adb shell`` is not).
  2. **Arguments** — the remaining tokens (the *tail*) must satisfy a per-key
     validator. This matters because ``adb shell`` re-joins its arguments into a
     string that the on-device shell parses, so an unvalidated argument like
     ``$(reboot)`` would be shell-interpreted on the phone. Every key has a
     validator; a key without one fails closed.

Commands are argv lists executed with ``shell=False``, so there is no host-side
shell. The argument validators close the device-side ``adb shell`` case and
option-injection (a value starting with ``-``).

Adding a capability means adding its sub-command AND its argument validator here
on purpose. A denied command is a bug or an attack, never something to "work
around" by shelling out directly.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from ..models import RiskLevel

# adb sub-commands the agent is allowed to run, grouped by the mission.
_ADB_ALLOWED: dict[str, str] = {
    # --- inspect / audit (read-only) ---
    "devices": "list connected devices",
    "get-state": "device connection state",
    "shell:getprop": "read a system property",
    "shell:pm list packages": "list installed packages",
    "shell:pm list permissions": "list permission definitions (read-only)",
    # Specific read-only dumpsys services only — NOT a blanket `dumpsys`.
    "shell:dumpsys package": "read package/permission info",
    "shell:dumpsys batterystats": "read battery usage stats",
    # Specific read-only cmd-package verb only — NOT a blanket `cmd package`,
    # which would also permit `uninstall` / `install-existing`.
    "shell:cmd package list packages": "list packages with uids",
    # --- optimize (reversible) ---
    "shell:pm disable-user": "disable (not remove) a package for the user",
    "shell:pm enable": "re-enable a previously disabled package",
    "shell:pm clear": "clear an app's cache/data",
}

# fastboot sub-commands.
_FASTBOOT_ALLOWED: dict[str, str] = {
    "devices": "list devices in bootloader mode",
    "getvar": "read a bootloader variable (e.g. unlocked state)",
    "flashing unlock": "unlock the bootloader of your own device (ERASES DATA)",
    "flashing lock": "re-lock the bootloader",
    "flash": "write an image to a partition",
    "reboot": "reboot the device",
}

_TOOLS = {"adb": _ADB_ALLOWED, "fastboot": _FASTBOOT_ALLOWED}

# Authoritative risk per full key (``tool:key``). The LLM's self-declared risk
# is never trusted over this; an allowlisted-but-unmapped key defaults to HIGH.
_RISK: dict[str, RiskLevel] = {
    "adb:devices": RiskLevel.NONE,
    "adb:get-state": RiskLevel.NONE,
    "adb:shell:getprop": RiskLevel.NONE,
    "adb:shell:pm list packages": RiskLevel.NONE,
    "adb:shell:pm list permissions": RiskLevel.NONE,
    "adb:shell:dumpsys package": RiskLevel.NONE,
    "adb:shell:dumpsys batterystats": RiskLevel.NONE,
    "adb:shell:cmd package list packages": RiskLevel.NONE,
    "adb:shell:pm disable-user": RiskLevel.LOW,
    "adb:shell:pm enable": RiskLevel.LOW,
    # `pm clear` wipes an app's entire data (not just cache); it is destructive
    # and NOT reversible, so it is HIGH, not LOW (audit M1).
    "adb:shell:pm clear": RiskLevel.HIGH,
    "fastboot:devices": RiskLevel.NONE,
    "fastboot:getvar": RiskLevel.NONE,
    "fastboot:reboot": RiskLevel.LOW,
    "fastboot:flashing unlock": RiskLevel.HIGH,
    "fastboot:flashing lock": RiskLevel.HIGH,
    "fastboot:flash": RiskLevel.HIGH,
}

# Authoritative reversibility per full key, derived here and never trusted from
# the LLM (audit M1). Only these two genuinely restore the prior state; a
# read-only (NONE-risk) command changes nothing and is treated as reversible by
# ``reversible_for``. Everything else (flash, unlock, pm clear, reboot) is NOT.
_REVERSIBLE: dict[str, bool] = {
    "adb:shell:pm disable-user": True,
    "adb:shell:pm enable": True,
}

# Safe value shapes. All forbid shell metacharacters by construction, and none
# may start with '-' (which fastboot/adb would read as an option — audit L6).
_PKG = re.compile(r"^[A-Za-z][A-Za-z0-9_.]*$")  # package id
_PROP = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")  # system property name
_VAR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")  # fastboot getvar variable
_PART = re.compile(r"^[A-Za-z0-9_]+$")  # fastboot partition name


_CONTROL = re.compile(r"[\x00-\x1f]")  # NUL, newline, tab, etc.


def _is_value(value: str) -> bool:
    """A non-option, non-empty host-side argv value — e.g. a ``fastboot flash``
    image path. It runs with ``shell=False`` and is never re-parsed by a shell,
    so legitimate path characters (``\\``, ``:``, spaces, ``()`` as in
    ``Program Files (x86)``) are fine; we only reject option-injection (a
    leading ``-``) and control characters that would corrupt argv or the log."""
    return bool(value) and not value.startswith("-") and not _CONTROL.search(value)


# Per-full-key argument validators. ``tail`` is the argv after the matched key
# (and after any stripped ``-s <serial>``). Every key MUST have one; a missing
# validator fails closed in ``validate``.
_ARGS: dict[str, Callable[[list[str]], bool]] = {
    "adb:devices": lambda t: t in ([], ["-l"]),
    "adb:get-state": lambda t: t == [],
    "adb:shell:getprop": lambda t: len(t) <= 1 and all(_PROP.fullmatch(x) for x in t),
    "adb:shell:pm list packages": lambda t: all(x in {"-3", "-d", "-e", "-s", "-U"} for x in t),
    "adb:shell:pm list permissions": lambda t: all(x in {"-g", "-f", "-d", "-u", "-s"} for x in t),
    "adb:shell:dumpsys package": lambda t: len(t) == 1 and bool(_PKG.fullmatch(t[0])),
    "adb:shell:dumpsys batterystats": lambda t: t == [],
    "adb:shell:cmd package list packages": lambda t: all(x in {"-U", "-3", "-d", "-e"} for x in t),
    "adb:shell:pm disable-user": lambda t: len(t) == 1 and bool(_PKG.fullmatch(t[0])),
    "adb:shell:pm enable": lambda t: len(t) == 1 and bool(_PKG.fullmatch(t[0])),
    "adb:shell:pm clear": lambda t: len(t) == 1 and bool(_PKG.fullmatch(t[0])),
    "fastboot:devices": lambda t: t == [],
    "fastboot:getvar": lambda t: len(t) == 1 and bool(_VAR.fullmatch(t[0])),
    "fastboot:flashing unlock": lambda t: t == [],
    "fastboot:flashing lock": lambda t: t == [],
    # partition name constrained; image path only guarded against option-injection
    # (it runs host-side with shell=False, so it is not shell-parsed).
    "fastboot:flash": lambda t: len(t) == 2 and bool(_PART.fullmatch(t[0])) and _is_value(t[1]),
    "fastboot:reboot": lambda t: t in ([], ["bootloader"]),
}

# Shell-significant characters. `adb shell` re-parses its arguments on the
# device, so any of these in a token is rejected outright as a second line of
# defense behind the per-key validators.
_META = re.compile(r"[;&|$`><\n\r(){}*?!\\\"']")


class CommandDenied(RuntimeError):
    """Raised when a proposed command is not permitted."""


def _strip_selector(argv: list[str]) -> list[str]:
    """argv after the tool, with a leading ``-s <serial>`` removed."""
    rest = argv[1:]
    if len(rest) >= 2 and rest[0] == "-s":
        rest = rest[2:]
    return rest


def _match_key(tool: str, rest: list[str]) -> str | None:
    """Longest allowlist key that prefixes ``rest`` (selector already stripped)."""
    allowed = _TOOLS.get(tool, {})
    if rest and rest[0] == "shell":
        prefix = "shell:" + " ".join(rest[1:])
    else:
        prefix = " ".join(rest)
    for key in sorted(allowed, key=len, reverse=True):
        if prefix == key or prefix.startswith(key + " "):
            return key
    return None


def _key_token_count(key: str) -> int:
    """How many argv tokens the matched key consumes."""
    if key.startswith("shell:"):
        sub = key[len("shell:") :]
        return 1 + (len(sub.split()) if sub else 0)
    return len(key.split())


def validate(command: list[str]) -> str:
    """Validate an argv command (shape + arguments). Returns the full key
    ``tool:key`` or raises ``CommandDenied``."""
    if not command:
        raise CommandDenied("empty command")
    tool = command[0]
    if tool not in _TOOLS:
        raise CommandDenied(f"tool {tool!r} is not allowed (only: {', '.join(_TOOLS)})")

    rest = _strip_selector(command)
    # Secondary guard against device-side shell reparse: `adb shell …` joins its
    # arguments into one string that the phone's shell parses, so any
    # shell-significant character there is rejected (defence in depth behind the
    # per-key validators). Host-side argv (fastboot, non-shell adb) runs with
    # shell=False and is governed by its per-key validator, so a file path with
    # a '\\', spaces or '()' is allowed — otherwise Windows image paths like
    # `C:\\…\\boot.img` could never be flashed.
    if rest and rest[0] == "shell" and any(_META.search(tok) for tok in rest[1:]):
        raise CommandDenied("shell-significant characters are not allowed in an adb shell argument")

    key = _match_key(tool, rest)
    if key is None:
        raise CommandDenied(
            f"{tool} sub-command not on allowlist: {' '.join(command[1:]) or '(none)'}"
        )
    full_key = f"{tool}:{key}"

    tail = rest[_key_token_count(key) :]
    validator = _ARGS.get(full_key)
    if validator is None or not validator(tail):
        raise CommandDenied(f"arguments not permitted for {full_key}: {' '.join(tail) or '(none)'}")
    return full_key


def risk_for(command: list[str]) -> RiskLevel:
    """Authoritative risk for a command, derived from the allowlist.

    Validates first (raising ``CommandDenied`` if not permitted), then returns
    the mapped risk. An allowlisted-but-unmapped key defaults to HIGH so a new
    entry is never silently treated as safe.
    """
    return _RISK.get(validate(command), RiskLevel.HIGH)


def reversible_for(command: list[str]) -> bool:
    """Authoritative reversibility for a command, derived from the allowlist.

    Validates first, then returns whether the action can be cleanly undone: the
    two explicitly reversible pm verbs, or any read-only (NONE-risk) command
    that changes nothing. Everything else is False. The LLM's self-declared
    ``reversible`` is never trusted over this (audit M1)."""
    key = validate(command)
    if _REVERSIBLE.get(key, False):
        return True
    return _RISK.get(key, RiskLevel.HIGH) is RiskLevel.NONE


def description_for(command: list[str]) -> str:
    """The canonical, repo-authored description of what a command does.

    Unlike ``Step.human`` (which the LLM writes), this text is fixed here, so it
    can be shown next to the raw argv for a trustworthy account of a step that
    does not depend on what the model chose to say (audit M2)."""
    full_key = validate(command)
    tool, key = full_key.split(":", 1)
    return _TOOLS.get(tool, {}).get(key, key)
