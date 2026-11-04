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
import sys
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


def _run_subprocess(argv: list[str], timeout: float | None) -> RunOutput:
    """Execute an argv list with ``shell=False`` and capture its output."""
    try:
        proc = subprocess.run(  # noqa: S603 - argv list, shell=False, allowlisted upstream
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except FileNotFoundError as exc:
        return RunOutput(127, "", str(exc))
    except subprocess.TimeoutExpired:
        return RunOutput(124, "", f"timed out after {timeout}s")
    return RunOutput(proc.returncode, proc.stdout, proc.stderr)


class Runner(Protocol):
    def run(self, command: list[str], timeout: float | None = 120.0) -> RunOutput: ...


class LocalRunner:
    """Run the toolchain directly on the host."""

    def run(self, command: list[str], timeout: float | None = 120.0) -> RunOutput:
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
        return _run_subprocess([exe, *command[1:]], timeout)


class ContainerRunner:
    """Run the toolchain inside a network-less container with the device
    reachable, so a compromised binary or a malicious device payload cannot
    reach the host filesystem or the internet.

    The *inner* command (``["adb", ...]`` / ``["fastboot", ...]``) is already
    allowlist-validated by ``Bridge`` before it reaches here; this runner only
    wraps it in a container invocation. Device access differs by OS:

      • **Linux** — pass the USB bus straight through and keep the container
        off the network::

            <engine> run --rm --network none --device=/dev/bus/usb IMAGE adb ...

      • **Windows / macOS** — the container can't see USB directly, so adb runs
        in *server* mode on the host and the container's adb/fastboot talks to
        it over a loopback socket (``-H host.docker.internal``). The container
        gets just that host gateway, nothing else.

    Requires ``podman`` or ``docker`` on PATH and an image with platform-tools
    installed (``image``). Build one from ``docker/adb-tools.Dockerfile``.
    """

    def __init__(
        self,
        image: str = "android-agent/adb-tools:latest",
        engine: str | None = None,
        platform: str | None = None,
    ) -> None:
        self.image = image
        self._engine = engine
        self.platform = platform or sys.platform

    def engine(self) -> str | None:
        """The container engine to use: explicit, else podman, else docker."""
        if self._engine:
            return self._engine
        return shutil.which("podman") and "podman" or (shutil.which("docker") and "docker") or None

    @property
    def _is_linux(self) -> bool:
        return self.platform.startswith("linux")

    def build_command(self, inner: list[str], engine: str) -> list[str]:
        """Wrap an inner adb/fastboot argv in a container run invocation.

        Pure and deterministic (no subprocess), so it is unit-tested per OS.
        """
        argv = [engine, "run", "--rm", "-i"]
        if self._is_linux:
            # USB passthrough; fully network-less.
            argv += ["--network", "none", "--device=/dev/bus/usb"]
            inner_cmd = inner
        else:
            # Reach the host's adb server over the Docker/Podman host gateway.
            argv += ["--add-host", "host.docker.internal:host-gateway"]
            tool, *tail = inner
            # adb accepts -H <host>; fastboot discovers over the same adb server.
            inner_cmd = [tool, "-H", "host.docker.internal", *tail] if tool == "adb" else inner
        argv += [self.image, *inner_cmd]
        return argv

    def run(self, command: list[str], timeout: float | None = 120.0) -> RunOutput:
        if not command:
            return RunOutput(2, "", "empty command")
        engine = self.engine()
        if engine is None:
            return RunOutput(
                127,
                "",
                "no container engine found. Install podman or docker, or use --runner local.",
            )
        return _run_subprocess(self.build_command(command, engine), timeout)
