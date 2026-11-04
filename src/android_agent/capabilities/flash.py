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
from ..models import Device, DeviceMode, Mission, Plan, RiskLevel, Step
from .base import Capability

# A sensible default order to flash partitions in. Partitions earlier in the
# list are written first; callers supply only the ones they have images for.
RECOMMENDED_PARTITION_ORDER: tuple[str, ...] = (
    "bootloader",
    "radio",
    "vbmeta",
    "dtbo",
    "boot",
    "init_boot",
    "vendor_boot",
    "super",
    "system",
    "vendor",
    "product",
)


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


def _reject_option_like(value: str, what: str) -> str:
    """Guard against argument injection: a partition or image path that starts
    with ``-`` could be parsed by fastboot as an option rather than a value.
    argv (no shell) already blocks command injection; this closes option
    injection too."""
    if value.startswith("-"):
        raise ValueError(f"{what} must not start with '-' (got {value!r})")
    if not value:
        raise ValueError(f"{what} must not be empty")
    return value


class FlashCapability(Capability):
    mission = "flash"

    def gather_facts(self, device: Device) -> dict:
        if device.mode is not DeviceMode.FASTBOOT:
            return {"error": "device must be in fastboot mode to flash"}
        product = self.bridge.execute(["fastboot", "-s", device.serial, "getvar", "product"])
        return {"product_raw": product.stderr or product.stdout}

    @staticmethod
    def flash_partition_step(serial: str, partition: str, image_path: str) -> Step:
        partition = _reject_option_like(partition, "partition")
        image_path = _reject_option_like(image_path, "image path")
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

    @staticmethod
    def order_partitions(images: dict[str, str]) -> list[tuple[str, str]]:
        """Order ``{partition: image_path}`` by the recommended flash order,
        with any unknown partitions appended alphabetically after the known
        ones (deterministic)."""
        known = [(p, images[p]) for p in RECOMMENDED_PARTITION_ORDER if p in images]
        rest = sorted((p, img) for p, img in images.items() if p not in RECOMMENDED_PARTITION_ORDER)
        return known + rest

    def build_rom_flash_plan(
        self, device: Device, expected_product: str, images: dict[str, str]
    ) -> Plan:
        """Deterministic, guarded walkthrough to flash a ROM (e.g. LineageOS).

        The caller MUST have confirmed the device is unlocked and backed up.
        This verifies the target first (raising on mismatch), then emits an
        ordered flash step per partition plus a final reboot.
        """
        self.require_target(device, expected_product)  # fail-safe before any step
        ordered = self.order_partitions(images)
        steps = [
            self.flash_partition_step(device.serial, partition, image)
            for partition, image in ordered
        ]
        steps.append(
            Step(
                capability="flash",
                human="Reboot the device to finish and boot the new ROM.",
                command=["fastboot", "-s", device.serial, "reboot"],
                risk=RiskLevel.HIGH,
                reversible=False,
            )
        )
        summary = (
            f"Flash {len(ordered)} partition(s) to '{expected_product}' in the "
            "recommended order, then reboot. HIGH risk: this can erase data and, "
            "if an image is wrong for your model, brick the device. The target "
            "has been verified against the connected device."
        )
        return Plan(mission=Mission.FLASH, summary=summary, steps=steps)
