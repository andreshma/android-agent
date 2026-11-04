"""The ROM flash walkthrough must be ordered and gated on the target."""

import pytest

from android_agent.bridge.sandbox import RunOutput
from android_agent.capabilities.flash import FlashCapability, FlashTargetMismatch
from android_agent.models import Device, DeviceMode, Mission, RiskLevel


class _FakeBridge:
    def __init__(self, getvar_output: str):
        self._out = getvar_output

    def execute(self, command, timeout: float = 120.0):
        return RunOutput(0, "", self._out)


def _fastboot_device() -> Device:
    return Device(serial="S1", mode=DeviceMode.FASTBOOT, authorized=True)


def test_order_partitions_follows_recommended_order():
    images = {"system": "s.img", "boot": "b.img", "vbmeta": "v.img"}
    ordered = FlashCapability.order_partitions(images)
    assert [p for p, _ in ordered] == ["vbmeta", "boot", "system"]


def test_order_partitions_appends_unknown_alphabetically():
    images = {"zebra": "z.img", "boot": "b.img", "alpha": "a.img"}
    ordered = FlashCapability.order_partitions(images)
    # boot (known) first, then unknown alpha, zebra sorted
    assert [p for p, _ in ordered] == ["boot", "alpha", "zebra"]


def test_build_rom_flash_plan_verified_and_ordered(tmp_path):
    boot = tmp_path / "b.img"
    system = tmp_path / "s.img"
    boot.write_bytes(b"x")
    system.write_bytes(b"x")
    cap = FlashCapability(_FakeBridge("(bootloader) product: redfin\n"))
    plan = cap.build_rom_flash_plan(
        _fastboot_device(), "redfin", {"system": str(system), "boot": str(boot)}
    )
    assert plan.mission is Mission.FLASH
    assert plan.max_risk is RiskLevel.HIGH
    # boot before system, plus a final reboot step
    cmds = [s.command for s in plan.steps]
    assert cmds[0][-2:] == ["boot", str(boot)]
    assert cmds[1][-2:] == ["system", str(system)]
    assert plan.steps[-1].command[-1] == "reboot"


def test_build_rom_flash_plan_refuses_on_mismatch(tmp_path):
    img = tmp_path / "b.img"
    img.write_bytes(b"x")
    cap = FlashCapability(_FakeBridge("(bootloader) product: bramble\n"))
    with pytest.raises(FlashTargetMismatch):
        cap.build_rom_flash_plan(_fastboot_device(), "redfin", {"boot": str(img)})


def test_build_rom_flash_plan_missing_image(tmp_path):
    cap = FlashCapability(_FakeBridge("(bootloader) product: redfin\n"))
    with pytest.raises(FileNotFoundError):
        cap.build_rom_flash_plan(_fastboot_device(), "redfin", {"boot": "nope.img"})


def test_flash_step_rejects_option_like_partition():
    # Argument-injection guard: a partition/image starting with '-' is refused.
    with pytest.raises(ValueError):
        FlashCapability.flash_partition_step("S1", "--version", "boot.img")
    with pytest.raises(ValueError):
        FlashCapability.flash_partition_step("S1", "boot", "-x")
