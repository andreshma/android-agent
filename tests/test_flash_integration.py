"""Real-subprocess integration tests for the `flash-rom` and `unlock` flows.

Unlike the fake-bridge end-to-end tests (`test_flows_e2e.py`), these drive the
code through the **real execution path**: `LocalRunner` spawns an actual process
(`shell=False`) and the output is parsed by the real parsers. The "device" is a
fake `adb`/`fastboot` executable stub pointed to by `ANDROID_AGENT_ADB` /
`ANDROID_AGENT_FASTBOOT`, so the whole chain — argv construction, process spawn,
`fastboot devices` / `getvar` parsing, the ordered partition flash, the reboot,
and the bootloader `flashing unlock` — is exercised without any hardware.

This is the one thing an emulator cannot give us: an AVD has no bootloader /
fastboot mode, so neither `flash-rom` nor `unlock` can ever run against it. The
stub lets us validate the real *flow* (not the flashing or the unlock itself,
which only real hardware can prove — the stub cannot reproduce a vendor
bootloader, its data wipe, or its on-screen confirmation).

POSIX only: the stub is an executable relying on a `#!` shebang. On Windows the
tool is launched via `CreateProcess` (`shell=False`), which won't exec a script
stub directly; Windows image-path handling is covered instead by the allowlist
unit tests (`test_allowlist_hardening.test_flash_allows_real_image_paths`).
"""

from __future__ import annotations

import stat
import sys
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from android_agent.cli import app

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="stub needs a POSIX shebang; Windows image paths covered by allowlist unit tests",
)

SERIAL = "STUB123"
PRODUCT = "redfin"

# A single stub that behaves as `adb` or `fastboot` depending on how it was
# invoked (argv[0] basename). It imitates the real tools closely enough for our
# parsers: `fastboot devices` prints "<serial>\tfastboot"; `getvar` prints on
# STDERR (as real fastboot does); `flash`/`reboot` are recorded to STUB_LOG.
_STUB_SOURCE = textwrap.dedent(
    '''\
    #!/usr/bin/env python3
    import os
    import sys

    name = os.path.basename(sys.argv[0])
    args = sys.argv[1:]
    log = os.environ.get("STUB_LOG")


    def record(line):
        if log:
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(line + "\\n")


    if name == "adb":
        # No adb-mode devices in this scenario: the phone is in fastboot mode.
        sys.exit(0)

    # ---- fastboot ----
    if args[:1] == ["devices"]:
        print("%s\\tfastboot" % os.environ.get("STUB_SERIAL", "STUB123"))
        sys.exit(0)

    # Drop a leading "-s <serial>" selector, like real fastboot accepts.
    if len(args) >= 2 and args[0] == "-s":
        args = args[2:]

    if args[:1] == ["getvar"] and len(args) >= 2:
        # Real fastboot prints getvar results on stderr.
        var = args[1]
        if var == "product":
            sys.stderr.write("product: %s\\n" % os.environ.get("STUB_PRODUCT", "redfin"))
        elif var == "unlocked":
            sys.stderr.write("unlocked: %s\\n" % os.environ.get("STUB_UNLOCKED", "no"))
        sys.stderr.write("finished. total time: 0.001s\\n")
        sys.exit(0)

    if args[:1] == ["flash"] and len(args) == 3:
        record("flash %s %s" % (args[1], args[2]))
        print("Sending '%s' (16 KB) OKAY" % args[1])
        print("Writing '%s' OKAY" % args[1])
        sys.exit(0)

    if args[:2] == ["flashing", "unlock"]:
        # The real bootloader also waits for an on-screen confirmation; the stub
        # just records that the unlock command reached fastboot intact.
        record("flashing unlock")
        print("OKAY")
        sys.exit(0)

    if args[:1] == ["reboot"]:
        record("reboot")
        sys.exit(0)

    sys.exit(0)
    '''
)


def _make_stubs(tmp_path: Path) -> tuple[str, str]:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    paths = []
    for tool in ("adb", "fastboot"):
        p = bindir / tool
        p.write_text(_STUB_SOURCE, encoding="utf-8")
        p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        paths.append(str(p))
    return paths[0], paths[1]


def _make_images(tmp_path: Path) -> dict[str, Path]:
    images = {}
    for part in ("boot", "system"):
        f = tmp_path / f"{part}.img"
        f.write_bytes(b"\x00" * 16)
        images[part] = f
    return images


@pytest.fixture
def stub_log(tmp_path, monkeypatch):
    """Install the adb/fastboot stubs via the env overrides; return the call log."""
    adb, fastboot = _make_stubs(tmp_path)
    monkeypatch.setenv("ANDROID_AGENT_ADB", adb)
    monkeypatch.setenv("ANDROID_AGENT_FASTBOOT", fastboot)
    monkeypatch.setenv("STUB_SERIAL", SERIAL)
    monkeypatch.setenv("STUB_PRODUCT", PRODUCT)
    log = tmp_path / "calls.log"
    monkeypatch.setenv("STUB_LOG", str(log))
    return log


def test_flash_rom_happy_path_real_subprocess(stub_log, tmp_path):
    """The full flash-rom flow drives real processes: discover -> verify target
    -> flash partitions in the recommended order -> reboot."""
    images = _make_images(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "flash-rom",
            "-s",
            SERIAL,
            "--product",
            PRODUCT,
            "--image",
            f"boot={images['boot']}",
            "--image",
            f"system={images['system']}",
            "--no-log",
        ],
        # consent "y", HIGH-risk typed "yes", run "y"
        input="y\nyes\ny\n",
    )

    assert result.exit_code == 0, result.output
    calls = stub_log.read_text(encoding="utf-8").splitlines()
    # boot is flashed before system (recommended order), then reboot — and the
    # real image paths reached fastboot intact through the process boundary.
    assert calls == [
        f"flash boot {images['boot']}",
        f"flash system {images['system']}",
        "reboot",
    ]


def test_flash_rom_refuses_wrong_target_real_subprocess(stub_log, tmp_path):
    """getvar reports 'redfin'; asking to flash 'sunfish' is refused before any
    partition is written — proving the live target check works over real I/O."""
    images = _make_images(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "flash-rom",
            "-s",
            SERIAL,
            "--product",
            "sunfish",
            "--image",
            f"boot={images['boot']}",
            "--no-log",
        ],
        input="y\n",  # consent only; it aborts at the target check
    )

    assert result.exit_code != 0
    assert "Refusing to flash" in result.output
    # Nothing was flashed.
    assert not stub_log.exists() or stub_log.read_text(encoding="utf-8") == ""


def test_devices_lists_fastboot_device_real_subprocess(stub_log):
    """`devices` end-to-end over real processes finds the stubbed fastboot device."""
    result = CliRunner().invoke(app, ["devices"])
    assert result.exit_code == 0, result.output
    assert SERIAL in result.output
    assert "fastboot" in result.output.lower()


def test_flash_rom_reorders_partitions_real_subprocess(stub_log, tmp_path):
    """Images given out of order still flash in the recommended order (boot before
    system) — the ordering logic holds over the real process boundary."""
    images = _make_images(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "flash-rom",
            "-s",
            SERIAL,
            "--product",
            PRODUCT,
            # Deliberately reversed: system first, boot second.
            "--image",
            f"system={images['system']}",
            "--image",
            f"boot={images['boot']}",
            "--no-log",
        ],
        input="y\nyes\ny\n",
    )

    assert result.exit_code == 0, result.output
    calls = stub_log.read_text(encoding="utf-8").splitlines()
    assert calls == [
        f"flash boot {images['boot']}",
        f"flash system {images['system']}",
        "reboot",
    ]


def test_unlock_flow_real_subprocess(stub_log):
    """The `unlock` flow over real processes: read the unlock state via a real
    `getvar unlocked`, then drive `fastboot flashing unlock` through `LocalRunner`
    so the HIGH-risk command reaches fastboot intact. The stub cannot reproduce a
    real bootloader's data wipe / on-screen prompt — it proves only the flow."""
    from android_agent.bridge.device import Bridge
    from android_agent.bridge.sandbox import LocalRunner
    from android_agent.capabilities.unlock import UnlockCapability
    from android_agent.consent import grant
    from android_agent.models import Device, DeviceMode

    bridge = Bridge(LocalRunner())
    cap = UnlockCapability(bridge)
    device = grant(Device(serial=SERIAL, mode=DeviceMode.FASTBOOT))

    # gather_facts reads the real `getvar unlocked` output (stderr, like fastboot).
    facts = cap.gather_facts(device)
    assert "unlocked" in facts["unlocked_raw"].lower()

    # Execute the unlock step through the real subprocess path.
    result = cap.execute_step(device, UnlockCapability.unlock_step(SERIAL))
    assert result.ok, result.error

    calls = stub_log.read_text(encoding="utf-8").splitlines()
    assert calls == ["flashing unlock"]


def test_unlock_blocked_without_consent_real_subprocess(stub_log):
    """The consent gate stops `flashing unlock` before it ever spawns a process:
    an un-authorized device raises, and nothing reaches the stub."""
    from android_agent.bridge.device import Bridge
    from android_agent.bridge.sandbox import LocalRunner
    from android_agent.capabilities.unlock import UnlockCapability
    from android_agent.consent import ConsentError
    from android_agent.models import Device, DeviceMode

    cap = UnlockCapability(Bridge(LocalRunner()))
    device = Device(serial=SERIAL, mode=DeviceMode.FASTBOOT)  # authorized=False

    with pytest.raises(ConsentError):
        cap.execute_step(device, UnlockCapability.unlock_step(SERIAL))

    # The HIGH-risk command never reached fastboot.
    assert not stub_log.exists() or stub_log.read_text(encoding="utf-8") == ""
