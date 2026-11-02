"""Flash mission — HIGH risk.

Guides flashing a custom ROM (e.g. LineageOS) or firmware via fastboot. Because
this can brick a device if the image doesn't match the exact model/variant,
the capability is built around guardrails:

  • verify device model/product against the image's declared target,
  • require a confirmed backup step first,
  • flash partition-by-partition with an explicit HIGH-risk confirmation.

The actual flashing is a deliberate stub: a contributor should implement image
verification and the per-partition flow with care. The guardrail shape is here.
"""

from __future__ import annotations

from ..models import Device, DeviceMode, RiskLevel, Step
from .base import Capability


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
        """Guardrail: refuse to flash if the device product doesn't match.

        TODO(contributors): read ``self.gather_facts(device)["product_raw"]``,
        parse it robustly, and compare against ``expected_product`` before any
        flash is allowed to proceed.
        """
        raise NotImplementedError(
            "verify_target: implement strict model/variant matching before flashing."
        )
