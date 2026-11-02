"""Consent gate must block execution on an un-cleared device."""

import pytest

from android_agent import consent
from android_agent.consent import ConsentError
from android_agent.models import Device, DeviceMode


def _device() -> Device:
    return Device(serial="TESTSERIAL", mode=DeviceMode.ADB)


def test_unauthorized_device_is_blocked():
    with pytest.raises(ConsentError):
        consent.require_authorized(_device())


def test_granted_device_passes():
    granted = consent.grant(_device())
    assert granted.authorized is True
    consent.require_authorized(granted)  # should not raise


def test_grant_does_not_mutate_original():
    original = _device()
    consent.grant(original)
    assert original.authorized is False
