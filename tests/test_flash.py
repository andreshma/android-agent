"""Flash target verification is the guardrail against bricking, so test it."""

import pytest

from android_agent.bridge.sandbox import RunOutput
from android_agent.capabilities.flash import (
    FlashCapability,
    FlashTargetMismatch,
    product_matches,
)
from android_agent.models import Device, DeviceMode


def test_product_matches_case_insensitive():
    out = "(bootloader) product: redfin\nOKAY [  0.001s]\n"
    assert product_matches(out, "redfin") is True
    assert product_matches(out, "REDFIN") is True


def test_product_matches_rejects_mismatch():
    out = "(bootloader) product: bramble\nOKAY\n"
    assert product_matches(out, "redfin") is False


def test_product_matches_refuses_when_unknown():
    # No product line -> never matches (fail safe).
    assert product_matches("OKAY\n", "redfin") is False


class _FakeBridge:
    """Minimal bridge stub returning a canned getvar response."""

    def __init__(self, getvar_output: str):
        self._out = getvar_output

    def execute(self, command, timeout: float = 120.0):
        return RunOutput(0, "", self._out)


def _fastboot_device() -> Device:
    return Device(serial="S1", mode=DeviceMode.FASTBOOT, authorized=True)


def test_require_target_passes_on_match():
    cap = FlashCapability(_FakeBridge("(bootloader) product: redfin\n"))
    cap.require_target(_fastboot_device(), "redfin")  # must not raise


def test_require_target_raises_on_mismatch():
    cap = FlashCapability(_FakeBridge("(bootloader) product: bramble\n"))
    with pytest.raises(FlashTargetMismatch):
        cap.require_target(_fastboot_device(), "redfin")


def test_verify_target_false_when_not_fastboot():
    cap = FlashCapability(_FakeBridge("(bootloader) product: redfin\n"))
    adb_device = Device(serial="S1", mode=DeviceMode.ADB, authorized=True)
    assert cap.verify_target(adb_device, "redfin") is False
