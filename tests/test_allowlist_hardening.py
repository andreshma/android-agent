"""Regression tests for the audit's High findings (H1, H3) in the allowlist."""

import pytest

from android_agent.bridge import allowlist
from android_agent.bridge.allowlist import CommandDenied


@pytest.mark.parametrize(
    "tail",
    [
        ["ro.x", "$(reboot)"],
        ["ro.x", "`id`"],
        ["ro.x", "&", "reboot"],
        ["ro.x", ">", "/sdcard/x"],
        ["ro.x", "<", "/x"],
        ["ro.x\nreboot"],
        ["ro.x", "|| id"],
    ],
)
def test_h1_shell_arg_injection_is_rejected(tail):
    # getprop takes at most one safe property name; injected shell syntax or
    # extra args must be denied (device re-parses `adb shell` args).
    with pytest.raises(CommandDenied):
        allowlist.validate(["adb", "shell", "getprop", *tail])


def test_h3_cmd_package_uninstall_denied():
    with pytest.raises(CommandDenied):
        allowlist.validate(["adb", "shell", "cmd", "package", "uninstall", "com.x"])
    with pytest.raises(CommandDenied):
        allowlist.validate(["adb", "shell", "cmd", "package", "install-existing", "com.x"])


def test_cmd_package_list_packages_allowed():
    assert (
        allowlist.validate(["adb", "shell", "cmd", "package", "list", "packages", "-U"])
        == "adb:shell:cmd package list packages"
    )


def test_backup_removed_from_allowlist():
    # `adb backup` was removed (unused, and `-f <hostpath>` was an arbitrary
    # host-file-overwrite vector).
    with pytest.raises(CommandDenied):
        allowlist.validate(["adb", "backup", "-f", "out.ab", "-all"])


def test_pm_disable_user_rejects_injection_in_package():
    with pytest.raises(CommandDenied):
        allowlist.validate(["adb", "shell", "pm", "disable-user", "com.x;reboot"])


def test_flash_rejects_option_like_partition_at_allowlist():
    with pytest.raises(CommandDenied):
        allowlist.validate(["fastboot", "flash", "--slot=all", "boot.img"])


def test_flash_rejects_option_like_image_path():
    with pytest.raises(CommandDenied):
        allowlist.validate(["fastboot", "flash", "boot", "-malicious"])


@pytest.mark.parametrize(
    "image_path",
    [
        r"C:\Users\me\roms\boot.img",  # Windows path (backslashes)
        r"C:\Program Files (x86)\roms\boot.img",  # spaces + parentheses
        "/home/me/roms/boot.img",  # POSIX path
        "./boot.img",  # relative
    ],
)
def test_flash_allows_real_image_paths(image_path):
    # The image path runs host-side with shell=False, so legitimate path
    # characters must be accepted (otherwise flashing is impossible on Windows).
    assert (
        allowlist.validate(["fastboot", "flash", "boot", image_path]) == "fastboot:flash"
    )


def test_flash_rejects_control_chars_in_image_path():
    with pytest.raises(CommandDenied):
        allowlist.validate(["fastboot", "flash", "boot", "boot\nimg"])
