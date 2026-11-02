"""Execution sandbox for bridge commands.

Two execution backends, chosen at runtime:

  • ``LocalRunner`` — runs adb/fastboot directly on this machine. Used when the
    operator is already working in a trusted environment.
  • ``ContainerRunner`` — runs the toolchain inside a container that has only
    the USB device passed through and no network. This is the "secure sandbox"
    from the project goal: even a compromised toolchain or a malicious device
    payload can't reach the host or the internet.

Both honor the allowlist (validation happens in ``Bridge``, above this layer),
and both execute argv lists with ``shell=False`` so nothing is ever interpreted
by a shell.

Cross-platform: tool executables are resolved with ``shutil.which``, which
honours ``PATHEXT`` on Windows (so ``adb`` finds ``adb.exe``) and the normal
PATH on Linux/macOS. Either tool's path can be overridden with the
``ANDROID_AGENT_ADB`` / ``ANDROID_AGENT_FASTBOOT`` environment variables.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Protocol


@dataclass
class RunOutput:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


_ENV_OVERRIDE = {"adb": "ANDROID_AGENT_ADB", "fastboot": "ANDROID_AGENT_FASTBOOT"}


def resolve_tool(name: str) -> str | None:
    """Return an absolute path to ``adb``/``fastboot`` or None if not found.

    Checks an explicit env override first, then PATH (``.exe`` aware on Windows).
    """
    override = os.environ.get(_ENV_OVERRIDE.get(name, ""))
    if override and os.path.isfile(override):
        return override
    return shutil.which(name)


class Runner(Protocol):
    def run(self, command: list[str], timeout: float = 120.0) -> RunOutput: ...


class LocalRunner:
    """Run the toolchain directly on the host."""

    def run(self, command: list[str], timeout: float = 120.0) -> RunOutput:
        if not command:
            return RunOutput(2, "", "empty command")
        exe = resolve_tool(command[0])
        if exe is None:
            return RunOutput(
                127,
                "",
                f"'{command[0]}' not found. Install platform-tools and ensure it is "
                f"on PATH, or set {_ENV_OVERRIDE.get(command[0], 'the tool path')}.",
            )
        argv = [exe, *command[1:]]
        try:
            proc = subprocess.run(  # noqa: S603 - argv list, shell=False, allowlisted upstream
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            return RunOutput(124, "", f"timed out after {timeout}s")
        return RunOutput(proc.returncode, proc.stdout, proc.stderr)


class ContainerRunner:
    """Run the toolchain inside a network-less container with the USB device
    passed through.

    TODO(contributors): implement with Podman/Docker. USB passthrough differs by
    OS:
      • Linux: pass the bus device, e.g.
            podman run --rm --network none --device=/dev/bus/usb adb-tools <cmd>
      • Windows/macOS: the container can't see USB directly; the common pattern
        is to run adb in *server* mode on the host and point the container's
        adb at it over a loopback socket (``adb -H host.docker.internal``),
        keeping the container itself network-less except for that socket.
    The interface must stay identical to ``LocalRunner``.
    """

    def __init__(self, image: str = "android-agent/adb-tools:latest") -> None:
        self.image = image

    def run(self, command: list[str], timeout: float = 120.0) -> RunOutput:
        raise NotImplementedError(
            "ContainerRunner is a stub. Contributions welcome — see the docstring. "
            "Use --runner local for now."
        )
