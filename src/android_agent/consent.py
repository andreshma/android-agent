"""Ownership & consent gate.

This is a deliberate first-class part of the design, not an afterthought. The
agent only ever operates on a device that is:

  1. physically connected to this machine (detected via the bridge), and
  2. explicitly confirmed by the operator as *their own device, which they
     are authorized to modify*.

Anything resembling bypassing a lock, FRP, or working on a device the operator
does not own is out of scope by design. The gate records an explicit,
per-serial acknowledgement so that destructive missions (flash, unlock) cannot
run against a device that never passed it.
"""

from __future__ import annotations

from .models import Device

_CONSENT_TEXT = """\
This tool will act on the device you have connected. By continuing you confirm:

  • This is YOUR device, or you are explicitly authorized to modify it.
  • You understand that HIGH-risk actions (flashing firmware, unlocking the
    bootloader) can ERASE ALL DATA and may void your warranty.
  • The agent will always explain a plan and wait for your confirmation before
    doing anything that changes the device.

The agent does not help bypass locks, Factory Reset Protection, or security on
a device you do not own. That is out of scope.
"""


class ConsentError(RuntimeError):
    """Raised when an action is attempted on a device that hasn't been cleared."""


def consent_prompt() -> str:
    """Return the text to show the operator before the first action."""
    return _CONSENT_TEXT


def grant(device: Device) -> Device:
    """Mark a device as authorized after the operator has acknowledged consent.

    Returns a copy with ``authorized=True``. The CLI is responsible for only
    calling this after a real, interactive acknowledgement.
    """
    return device.model_copy(update={"authorized": True})


def require_authorized(device: Device) -> None:
    """Guard called by capabilities before they execute anything."""
    if not device.authorized:
        raise ConsentError(
            f"Device {device.serial} has not passed the ownership/consent gate. "
            "Run the consent step first."
        )
