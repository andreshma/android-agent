"""Flash mission — HIGH risk.

Guides flashing a custom ROM (e.g. LineageOS) or firmware via fastboot. Because
this can brick a device if the image doesn't match the exact model/variant,
the capability is built around guardrails:

  • verify device model/product against the image's declared target,
  • require a confirmed backup step first,
  • flash partition-by-partition with an explicit HIGH-risk confirmation.
"""

from __future__ import annotations

from ..bridge import parse
from ..models import Device, DeviceMode, RiskLevel, Step
from .base import Capability


class FlashTargetMismatch(RuntimeError):
    """Raised when the connected device is not the expected flash target."""


def product_matches(getvar_output: str, expected_product: str) -> bool:
    """Compare the device's ``product`` (from ``fastboot getvar product``)
    against the image's declared target, case-insensitively. A missing product
    never matches — we refuse to flash when we can't confirm the model."""
    product = parse.parse_getvar(getvar_output, "product")
    if not product:
        return False
    return product.strip().casefold() == expected_product.strip().casefold()


class FlashCapability(Capability):
    mission = "flash"

    def gather_facts(self, device: Device) -> dict:
        if device.mode is not DeviceMode.FASTBOOT:
            return {"error": "device must be in fastboot mode to flash"}
        product = self.bridge.execute(["fastboot", "-s", device.serial, "getvar", "product"])
        return {"product_raw": product.stderr or product.stdout}

    @staticmethod
    def flash_partition_step(serial: str, partition: str, image_path: str) -> Step:
        return Step(
            capability="flash",
            human=(
                f"Write the image '{image_path}' to the '{partition}' partition. "
                "This is HIGH risk and can erase data or brick the device if the "
                "image does not match your exact model."
            ),
            command=["fastboot", "-s", serial, "flash", partition, image_path],
            risk=RiskLevel.HIGH,
            reversible=False,
        )

    def verify_target(self, device: Device, expected_product: str) -> bool:
        """Return True only if the connected device's product matches
        ``expected_product``. Reads ``fastboot getvar product`` live."""
        if device.mode is not DeviceMode.FASTBOOT:
            return False
        out = self.bridge.execute(["fastboot", "-s", device.serial, "getvar", "product"])
        return product_matches(out.stderr or out.stdout, expected_product)

    def require_target(self, device: Device, expected_product: str) -> None:
        """Guardrail: raise unless the device is the expected target. Call this
        before building or running any flash step."""
        if not self.verify_target(device, expected_product):
            raise FlashTargetMismatch(
                f"Device {device.serial} is not the expected flash target "
                f"'{expected_product}'. Refusing to flash to avoid bricking it."
            )
