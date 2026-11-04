"""End-to-end CLI tests driving the consent -> confirm -> execute flow with a
fake bridge, so the command wiring itself is covered (not just the pieces)."""

from typer.testing import CliRunner

from android_agent import cli
from android_agent.bridge.sandbox import RunOutput
from android_agent.models import Device, DeviceMode

runner = CliRunner()


class _FakeBridge:
    """Canned responses keyed by a recognizable token in the command."""

    def __init__(self, device: Device | None):
        self._device = device

    def find_device(self, serial: str):
        return self._device

    def execute(self, command, timeout: float = 120.0) -> RunOutput:
        joined = " ".join(command)
        if "pm list packages -d" in joined:
            return RunOutput(0, "", "")  # nothing disabled yet
        if "pm list packages" in joined:
            return RunOutput(0, "package:com.facebook.katana\npackage:com.example.safe\n", "")
        if "batterystats" in joined:
            return RunOutput(0, "Estimated power use (mAh):\n", "")
        if "cmd package list packages -U" in joined:
            return RunOutput(0, "", "")
        if "disable-user" in joined:
            return RunOutput(0, "Package com.facebook.katana new state: disabled-user", "")
        return RunOutput(0, "", "")


def _patch_bridge(monkeypatch, device):
    monkeypatch.setattr(cli, "_build_bridge", lambda cfg: _FakeBridge(device))


def test_devices_none(monkeypatch):
    _patch_bridge(monkeypatch, None)
    # list_devices isn't on the fake; devices command calls it, so give it one.
    monkeypatch.setattr(_FakeBridge, "list_devices", lambda self: [], raising=False)
    result = runner.invoke(cli.app, ["devices"])
    assert result.exit_code == 0
    assert "No devices detected" in result.stdout


def test_debloat_happy_path(monkeypatch):
    device = Device(serial="S1", mode=DeviceMode.ADB)
    _patch_bridge(monkeypatch, device)
    # consent 'y', then run 'y'
    result = runner.invoke(cli.app, ["debloat", "-s", "S1", "--no-log"], input="y\ny\n")
    assert result.exit_code == 0
    assert "com.facebook.katana" in result.stdout
    assert "ok" in result.stdout
    # the safe app must not be in the plan
    assert "com.example.safe" not in result.stdout


def test_debloat_wrong_mode_aborts(monkeypatch):
    # A device in fastboot can't be debloated (needs adb).
    device = Device(serial="S1", mode=DeviceMode.FASTBOOT)
    _patch_bridge(monkeypatch, device)
    result = runner.invoke(cli.app, ["debloat", "-s", "S1", "--no-log"])
    assert result.exit_code != 0
    assert "adb mode" in result.stdout


def test_debloat_consent_decline_aborts(monkeypatch):
    device = Device(serial="S1", mode=DeviceMode.ADB)
    _patch_bridge(monkeypatch, device)
    result = runner.invoke(cli.app, ["debloat", "-s", "S1", "--no-log"], input="n\n")
    assert result.exit_code != 0
    # nothing was executed
    assert "ok" not in result.stdout


def test_log_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("ANDROID_AGENT_LOG", str(tmp_path / "actions.jsonl"))
    result = runner.invoke(cli.app, ["log"])
    assert result.exit_code == 0
    assert "No logged actions yet" in result.stdout
