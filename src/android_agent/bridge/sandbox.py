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
import uuid
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

# Secrets that must never be inherited by the adb/fastboot child process: the
# device toolchain has no business reading the operator's credentials (audit
# L3/L5). A strict allowlist would risk stripping env the tool genuinely needs
# across platforms (PATH, HOME, SystemRoot, locale, …) and would break on an
# unusual setup, so this is a credential-shaped DENYLIST: exact known keys plus
# any var whose name looks like a token/secret/key/password or belongs to a
# cloud/CI credential family. The goal — no credential reaches adb/fastboot — is
# met without guessing the full set of names the toolchain needs.
_SCRUBBED_ENV_KEYS = frozenset({"ANTHROPIC_API_KEY", "OPENAI_API_KEY"})
_SCRUBBED_ENV_SUFFIXES = ("_API_KEY", "_TOKEN", "_SECRET", "_PASSWORD", "_KEY", "_CREDENTIALS")
_SCRUBBED_ENV_PREFIXES = ("AWS_", "GOOGLE_", "GCP_", "AZURE_", "GH_", "GITHUB_")


def _is_secret_env_key(name: str) -> bool:
    upper = name.upper()
    return (
        name in _SCRUBBED_ENV_KEYS
        or upper.endswith(_SCRUBBED_ENV_SUFFIXES)
        or upper.startswith(_SCRUBBED_ENV_PREFIXES)
    )


def _child_env() -> dict[str, str]:
    """A copy of the environment with credential-shaped vars removed."""
    return {k: v for k, v in os.environ.items() if not _is_secret_env_key(k)}


def resolve_tool(name: str) -> str | None:
    """Return an absolute path to ``adb``/``fastboot`` or None if not found.

    Checks an explicit env override first, then PATH (``.exe`` aware on Windows).
    On Python < 3.12, ``shutil.which`` on Windows searches the current directory
    first, so a planted ``adb.exe`` in the CWD could shadow the real one; we
    reject a hit that resolves into the CWD unless it was an explicit override
    (audit L3).
    """
    override = os.environ.get(_ENV_OVERRIDE.get(name, ""))
    if override and os.path.isfile(override):
        return override
    found = shutil.which(name)
    if found and sys.platform == "win32":
        try:
            if os.path.dirname(os.path.abspath(found)) == os.getcwd():
                return None
        except OSError:
            return None
    return found


def _run_subprocess(argv: list[str], timeout: float | None) -> RunOutput:
    """Execute an argv list with ``shell=False`` and capture its output."""
    try:
        proc = subprocess.run(  # noqa: S603 - argv list, shell=False, allowlisted upstream
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            # Never inherit this process's stdin: the toolchain should not be
            # able to read from (or block on) the operator's terminal (audit L7).
            stdin=subprocess.DEVNULL,
            env=_child_env(),
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
    """Run the toolchain inside a hardened container with the device reachable,
    so a compromised binary or a malicious device payload is contained.

    **EXPERIMENTAL / unverified on hardware.** The container flow has not been
    run against a physical phone by the maintainer: the Linux USB-passthrough +
    per-call ephemeral adb key path (the device re-prompts "Allow USB
    debugging?" for a new key each run) and udev device-node permissions are
    untested live. Prefer ``--runner local`` until you have validated this on a
    spare device. See docs/TESTING.md.

    The *inner* command (``["adb", ...]`` / ``["fastboot", ...]``) is already
    allowlist-validated by ``Bridge`` before it reaches here; this runner only
    wraps it in a container invocation. Device access and network isolation
    differ by OS — note the isolation is NOT uniform:

      • **Linux** — USB bus passed straight through and the container kept fully
        **off the network** (``--network none``)::

            <engine> run --rm --network none --device=/dev/bus/usb IMAGE adb ...

      • **Windows / macOS** — the container can't see USB directly, so adb runs
        in *server* mode on the host and the container's adb/fastboot talks to
        it over the host gateway (``-H host.docker.internal``). This path is
        therefore **NOT network-less**: the container reaches the host gateway
        (needed for the adb server) rather than being isolated like on Linux.

    Any argv token that is an existing host file (e.g. a ROM image for
    ``fastboot flash``) is bind-mounted **read-only** into the container and the
    token rewritten to its in-container path, so flashing works in the sandbox
    too (on Linux, where USB is passed through).

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
        """The container engine to use, as an ABSOLUTE path: explicit, else
        podman, else docker. Resolving to a full path means the engine is never
        looked up from the CWD at spawn time (audit L10)."""
        name = self._engine or (
            "podman" if shutil.which("podman") else ("docker" if shutil.which("docker") else None)
        )
        if name is None:
            return None
        # If it resolves on PATH, use the absolute path; otherwise fall back to
        # the name (an explicit engine the caller vouches for).
        return shutil.which(name) or name

    @property
    def _is_linux(self) -> bool:
        return self.platform.startswith("linux")

    # Hardening applied to every container run (audit M3). Added unconditionally
    # so the sandbox is least-privilege by default; USB device-node access is
    # file-permission based, so dropping all capabilities does not block it.
    #
    #   --security-opt=no-new-privileges  no setuid escalation inside
    #   --cap-drop=ALL                    no Linux capabilities
    #   --read-only + --tmpfs=/tmp        immutable root fs, writable scratch
    #   -e HOME=/tmp                      adb keeps its key in the tmpfs
    #   --pids-limit / --memory           blast-radius limits on a bad binary
    _HARDENING = (
        "--security-opt=no-new-privileges",
        "--cap-drop=ALL",
        "--read-only",
        "--tmpfs=/tmp",
        "-e",
        "HOME=/tmp",
        "--pids-limit=512",
        "--memory=2g",
    )

    @staticmethod
    def mounts_for(command: list[str]) -> dict[str, str]:
        """Map any argv token that is an existing host file to a container path.

        ``fastboot flash boot boot.img`` can only work inside the sandbox if the
        image file is mounted in, so the toolchain can read it. We mount each
        such file **read-only** (the sandbox never needs to modify an image) at a
        stable ``/mnt/img/<n>_<name>`` path. Does a read-only ``isfile`` probe,
        so it lives in ``run`` (which already does I/O), not ``build_command``.
        """
        mounts: dict[str, str] = {}
        for tok in command:
            if tok in mounts:
                continue
            try:
                if os.path.isfile(tok):
                    mounts[tok] = f"/mnt/img/{len(mounts)}_{os.path.basename(tok)}"
            except OSError:
                continue
        return mounts

    def build_command(
        self, inner: list[str], engine: str, mounts: dict[str, str] | None = None
    ) -> list[str]:
        """Wrap an inner adb/fastboot argv in a container run invocation.

        ``mounts`` maps host file paths (as they appear in ``inner``) to the
        read-only container paths they are bound to; those tokens are rewritten
        to their container path so the tool reads the file from inside the
        sandbox. Pure and deterministic given ``mounts`` (no subprocess), so it
        is unit-tested per OS.
        """
        mounts = mounts or {}
        # No `-i`: stdin is attached to DEVNULL in _run_subprocess, so an
        # interactive TTY is neither needed nor wanted (audit L7).
        argv = [engine, "run", "--rm", *self._HARDENING]
        for host, container in mounts.items():
            argv += ["-v", f"{host}:{container}:ro"]

        def rewrite(tokens: list[str]) -> list[str]:
            return [mounts.get(t, t) for t in tokens]

        if self._is_linux:
            # USB passthrough; fully network-less.
            argv += ["--network", "none", "--device=/dev/bus/usb"]
            inner_cmd = rewrite(inner)
        else:
            # Reach the host's adb server over the Docker/Podman host gateway.
            argv += ["--add-host", "host.docker.internal:host-gateway"]
            tool, *tail = inner
            tail = rewrite(tail)
            # adb accepts -H <host>; fastboot discovers over the same adb server.
            if tool == "adb":
                inner_cmd = [tool, "-H", "host.docker.internal", *tail]
            else:
                inner_cmd = [tool, *tail]
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
        mounts = self.mounts_for(command)
        argv = self.build_command(command, engine, mounts)
        # Give the container a unique name and tear it down if it outlives the
        # timeout, so a hung toolchain doesn't leave an orphan container (L7).
        name = f"android-agent-{uuid.uuid4().hex[:12]}"
        argv = [argv[0], argv[1], f"--name={name}", *argv[2:]]
        out = _run_subprocess(argv, timeout)
        if out.returncode == 124:  # timed out
            subprocess.run(  # noqa: S603 - fixed argv, shell=False
                [engine, "rm", "-f", name],
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                env=_child_env(),
            )
        return out
