"""The allowlist is the security boundary, so it gets real tests."""

import pytest

from android_agent.bridge import allowlist
from android_agent.bridge.allowlist import CommandDenied


def test_allows_known_adb_readonly():
    assert allowlist.validate(["adb", "devices"]) == "adb:devices"


def test_allows_shell_subcommand():
    key = allowlist.validate(["adb", "-s", "X", "shell", "pm", "list", "packages"])
    assert key == "adb:shell:pm list packages"


def test_allows_reversible_optimize():
    key = allowlist.validate(["adb", "-s", "X", "shell", "pm", "disable-user", "com.x.news"])
    assert key == "adb:shell:pm disable-user"


def test_denies_unknown_tool():
    with pytest.raises(CommandDenied):
        allowlist.validate(["rm", "-rf", "/"])


def test_denies_arbitrary_shell():
    with pytest.raises(CommandDenied):
        allowlist.validate(["adb", "shell", "rm", "-rf", "/sdcard"])


def test_denies_shell_metacharacters():
    with pytest.raises(CommandDenied):
        allowlist.validate(["adb", "shell", "getprop;", "reboot"])


def test_high_risk_fastboot_is_allowed_but_tagged():
    # The allowlist permits it; HIGH-risk *confirmation* is enforced upstream.
    assert allowlist.validate(["fastboot", "flashing", "unlock"]) == "fastboot:flashing unlock"
