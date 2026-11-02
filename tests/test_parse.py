"""Parsers must handle real adb/fastboot output on any OS."""

from android_agent.bridge import parse
from android_agent.bridge.device import with_serial
from android_agent.models import DeviceMode

ADB_OUTPUT = """\
List of devices attached
ABCD1234               device usb:1-1 product:redfin model:Pixel_5 device:redfin transport_id:1
OFFLINE99              offline
UNAUTH00               unauthorized
"""

FASTBOOT_OUTPUT = "WXYZ5678\tfastboot\n"


def test_parse_adb_devices_online_only():
    devices = parse.parse_adb_devices(ADB_OUTPUT)
    assert len(devices) == 1
    d = devices[0]
    assert d.serial == "ABCD1234"
    assert d.mode is DeviceMode.ADB
    assert d.model == "Pixel_5"
    assert d.product == "redfin"


def test_parse_fastboot_devices():
    devices = parse.parse_fastboot_devices(FASTBOOT_OUTPUT)
    assert len(devices) == 1
    assert devices[0].serial == "WXYZ5678"
    assert devices[0].mode is DeviceMode.FASTBOOT


def test_parse_getvar():
    err = "(bootloader) unlocked: yes\nOKAY [  0.001s]\n"
    assert parse.parse_getvar(err, "unlocked") == "yes"


def test_with_serial_injects_selector():
    cmd = with_serial(["adb", "shell", "pm", "list", "packages"], "ABCD1234")
    assert cmd == ["adb", "-s", "ABCD1234", "shell", "pm", "list", "packages"]


def test_with_serial_skips_devices_subcommand():
    assert with_serial(["adb", "devices", "-l"], "ABCD1234") == ["adb", "devices", "-l"]


def test_with_serial_is_idempotent():
    cmd = ["adb", "-s", "OTHER", "shell", "getprop"]
    assert with_serial(cmd, "ABCD1234") == cmd
