"""End-to-end emulation of every user flow.

Drives the real CLI (Typer's CliRunner) through the full consent → plan →
confirm → execute → log path for each command, with a fake device bridge and a
fake LLM. No real device, network, or model is touched; this proves the wiring
of every flow a user can run, including the destructive ones.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from android_agent import cli
from android_agent.audit_log import ActionLog
from android_agent.bridge.sandbox import RunOutput
from android_agent.models import Device, DeviceMode, Mission, Plan, RiskLevel, Step

runner = CliRunner()


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class FakeBridge:
    """Canned adb/fastboot responses; records every executed command."""

    def __init__(self, devices: list[Device]):
        self._devices = {d.serial: d for d in devices}
        self.calls: list[list[str]] = []

    def list_devices(self) -> list[Device]:
        return list(self._devices.values())

    def find_device(self, serial: str):
        return self._devices.get(serial)

    def read_property(self, device: Device, prop: str):
        return {"ro.product.model": "FakePixel", "ro.build.version.release": "14"}.get(prop, "")

    def execute(self, command, timeout=None) -> RunOutput:
        self.calls.append(list(command))
        joined = " ".join(command)
        if "getvar product" in joined:
            return RunOutput(0, "", "product: redfin\n")
        if "getvar unlocked" in joined:
            return RunOutput(0, "", "unlocked: no\n")
        if "disable-user com.fail.app" in joined:
            return RunOutput(1, "", "disable failed")
        if "pm list packages -d" in joined:
            return RunOutput(0, "", "")
        if "pm list packages -3" in joined:
            return RunOutput(0, "package:com.facebook.katana\n", "")
        if "pm list packages" in joined:
            return RunOutput(0, "package:com.facebook.katana\npackage:com.example.safe\n", "")
        if "batterystats" in joined:
            return RunOutput(0, "Estimated power use (mAh):\n", "")
        if "package list packages -U" in joined:
            return RunOutput(0, "", "")
        return RunOutput(0, "", "")

    def ran(self, needle: str) -> bool:
        return any(needle in " ".join(c) for c in self.calls)


def _fake_llm(plan_builder):
    class _LLM:
        name = "fake"

        def propose_plan(self, *, mission, request, device_facts):
            return plan_builder(mission)

        def explain(self, text):  # pragma: no cover
            return text

    return _LLM()


def _patch(monkeypatch, bridge, llm=None):
    monkeypatch.setattr(cli, "_build_bridge", lambda cfg: bridge)
    if llm is not None:
        monkeypatch.setattr(cli, "make_llm", lambda backend, **kw: llm)


def _adb(serial="S1"):
    return Device(serial=serial, mode=DeviceMode.ADB, model="Pixel_5")


def _fastboot(serial="S1"):
    return Device(serial=serial, mode=DeviceMode.FASTBOOT)


def _step(cap, human, command, risk=RiskLevel.NONE, reversible=True, undo=None):
    return Step(capability=cap, human=human, command=command, risk=risk,
                reversible=reversible, undo=undo)


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def test_devices_lists_both_modes(monkeypatch):
    bridge = FakeBridge([_adb("AAA"), _fastboot("BBB")])
    _patch(monkeypatch, bridge)
    result = runner.invoke(cli.app, ["devices"])
    assert result.exit_code == 0
    assert "AAA" in result.stdout and "BBB" in result.stdout


# --------------------------------------------------------------------------- #
# Audit (read-only, LLM)
# --------------------------------------------------------------------------- #
def test_run_audit(monkeypatch):
    bridge = FakeBridge([_adb()])
    llm = _fake_llm(
        lambda m: Plan(
            mission=m,
            summary="Read the Android version.",
            steps=[_step("audit", "Read the Android version",
                         ["adb", "shell", "getprop", "ro.build.version.release"])],
        )
    )
    _patch(monkeypatch, bridge, llm)
    result = runner.invoke(cli.app, ["run", "audit", "what version", "-s", "S1", "--no-log"],
                           input="y\ny\n")
    assert result.exit_code == 0, result.stdout
    assert "Read the Android version" in result.stdout
    assert "ok" in result.stdout


# --------------------------------------------------------------------------- #
# Optimize (LLM) + stop-on-failure
# --------------------------------------------------------------------------- #
def test_run_optimize(monkeypatch):
    bridge = FakeBridge([_adb()])
    llm = _fake_llm(
        lambda m: Plan(
            mission=m,
            summary="Disable one app.",
            steps=[_step("optimize", "Disable the news app",
                         ["adb", "shell", "pm", "disable-user", "com.x.news"],
                         risk=RiskLevel.LOW, undo=["adb", "shell", "pm", "enable", "com.x.news"])],
        )
    )
    _patch(monkeypatch, bridge, llm)
    result = runner.invoke(cli.app, ["run", "optimize", "declutter", "-s", "S1", "--no-log"],
                           input="y\ny\n")
    assert result.exit_code == 0, result.stdout
    assert bridge.ran("disable-user com.x.news")


def test_run_stops_after_failed_step(monkeypatch):
    bridge = FakeBridge([_adb()])
    llm = _fake_llm(
        lambda m: Plan(
            mission=m,
            summary="Disable two apps.",
            steps=[
                _step("optimize", "Disable failing app",
                      ["adb", "shell", "pm", "disable-user", "com.fail.app"], risk=RiskLevel.LOW),
                _step("optimize", "Disable second app",
                      ["adb", "shell", "pm", "disable-user", "com.other.app"], risk=RiskLevel.LOW),
            ],
        )
    )
    _patch(monkeypatch, bridge, llm)
    result = runner.invoke(cli.app, ["run", "optimize", "x", "-s", "S1", "--no-log"],
                           input="y\ny\n")
    assert result.exit_code == 0, result.stdout
    # first failed; the second must be skipped, never executed
    assert "Stopped after a failed step" in result.stdout
    assert not bridge.ran("disable-user com.other.app")


# --------------------------------------------------------------------------- #
# Debloat (deterministic)
# --------------------------------------------------------------------------- #
def test_debloat(monkeypatch):
    bridge = FakeBridge([_adb()])
    _patch(monkeypatch, bridge)
    result = runner.invoke(cli.app, ["debloat", "-s", "S1", "--no-log"], input="y\ny\n")
    assert result.exit_code == 0, result.stdout
    assert "com.facebook.katana" in result.stdout
    assert "com.example.safe" not in result.stdout  # non-bloatware untouched


# --------------------------------------------------------------------------- #
# Flash (deterministic flash-rom, HIGH risk, typed-yes)
# --------------------------------------------------------------------------- #
def test_flash_rom(monkeypatch, tmp_path):
    boot = tmp_path / "boot.img"
    system = tmp_path / "system.img"
    boot.write_bytes(b"BOOT")
    system.write_bytes(b"SYSTEM")
    bridge = FakeBridge([_fastboot()])
    _patch(monkeypatch, bridge)
    result = runner.invoke(
        cli.app,
        ["flash-rom", "-s", "S1", "--product", "redfin",
         "--image", f"boot={boot}", "--image", f"system={system}", "--no-log"],
        input="y\nyes\ny\n",  # consent, typed HIGH 'yes', run
    )
    assert result.exit_code == 0, result.stdout
    assert bridge.ran("flash boot")
    assert bridge.ran("flash system")
    assert bridge.ran("reboot")


def test_flash_rom_refuses_wrong_product(monkeypatch, tmp_path):
    boot = tmp_path / "boot.img"
    boot.write_bytes(b"BOOT")
    bridge = FakeBridge([_fastboot()])  # reports product 'redfin'
    _patch(monkeypatch, bridge)
    result = runner.invoke(
        cli.app,
        ["flash-rom", "-s", "S1", "--product", "sunfish", "--image", f"boot={boot}", "--no-log"],
        input="y\n",
    )
    assert result.exit_code != 0
    assert "Refusing to flash" in result.stdout
    assert not bridge.ran("flash boot")


def test_high_risk_rejects_bare_y(monkeypatch, tmp_path):
    boot = tmp_path / "boot.img"
    boot.write_bytes(b"BOOT")
    bridge = FakeBridge([_fastboot()])
    _patch(monkeypatch, bridge)
    # consent 'y', then a bare 'y' at the typed-yes gate must abort
    result = runner.invoke(
        cli.app,
        ["flash-rom", "-s", "S1", "--product", "redfin", "--image", f"boot={boot}", "--no-log"],
        input="y\ny\n",
    )
    assert result.exit_code != 0
    assert not bridge.ran("flash boot")


# --------------------------------------------------------------------------- #
# Unlock (LLM, HIGH risk)
# --------------------------------------------------------------------------- #
def test_run_unlock(monkeypatch):
    bridge = FakeBridge([_fastboot()])
    llm = _fake_llm(
        lambda m: Plan(
            mission=m,
            summary="Unlock the bootloader.",
            steps=[_step("unlock", "Unlock the bootloader (erases data)",
                         ["fastboot", "flashing", "unlock"],
                         risk=RiskLevel.HIGH, reversible=False)],
        )
    )
    _patch(monkeypatch, bridge, llm)
    result = runner.invoke(cli.app, ["run", "unlock", "unlock my bootloader", "-s", "S1",
                                     "--no-log"], input="y\nyes\ny\n")
    assert result.exit_code == 0, result.stdout
    assert bridge.ran("flashing unlock")


# --------------------------------------------------------------------------- #
# Guard rails
# --------------------------------------------------------------------------- #
def test_consent_decline_aborts(monkeypatch):
    bridge = FakeBridge([_adb()])
    _patch(monkeypatch, bridge)
    result = runner.invoke(cli.app, ["debloat", "-s", "S1", "--no-log"], input="n\n")
    assert result.exit_code != 0
    assert not bridge.ran("disable-user")


def test_wrong_mode_aborts(monkeypatch):
    bridge = FakeBridge([_fastboot()])  # fastboot can't be audited
    llm = _fake_llm(lambda m: Plan(mission=m, summary="", steps=[]))
    _patch(monkeypatch, bridge, llm)
    result = runner.invoke(cli.app, ["run", "audit", "x", "-s", "S1", "--no-log"])
    assert result.exit_code != 0
    assert "adb mode" in result.stdout


def test_offmission_plan_rejected(monkeypatch):
    bridge = FakeBridge([_adb()])
    llm = _fake_llm(
        lambda m: Plan(
            mission=m,
            summary="sneaky",
            steps=[_step("audit", "wipe", ["fastboot", "flash", "system", "evil.img"])],
        )
    )
    _patch(monkeypatch, bridge, llm)
    result = runner.invoke(cli.app, ["run", "audit", "x", "-s", "S1", "--no-log"], input="y\n")
    assert result.exit_code != 0
    assert "Rejected" in result.stdout
    assert not bridge.ran("flash system")


def test_device_not_found_aborts(monkeypatch):
    bridge = FakeBridge([])
    _patch(monkeypatch, bridge)
    result = runner.invoke(cli.app, ["debloat", "-s", "NOPE", "--no-log"])
    assert result.exit_code != 0
    assert "not found" in result.stdout


# --------------------------------------------------------------------------- #
# Hosted-backend egress + logging
# --------------------------------------------------------------------------- #
def test_hosted_backend_discloses_egress(monkeypatch):
    bridge = FakeBridge([_adb()])
    llm = _fake_llm(
        lambda m: Plan(mission=m, summary="noop",
                       steps=[_step("audit", "read", ["adb", "shell", "getprop", "ro.x"])])
    )
    _patch(monkeypatch, bridge, llm)
    result = runner.invoke(
        cli.app, ["run", "audit", "x", "-s", "S1", "--llm", "anthropic", "--no-log"],
        input="y\ny\n",
    )
    assert result.exit_code == 0, result.stdout
    assert "Data leaves your machine" in result.stdout


def test_flow_writes_verifiable_log(monkeypatch, tmp_path):
    monkeypatch.setenv("ANDROID_AGENT_LOG", str(tmp_path / "actions.jsonl"))
    bridge = FakeBridge([_adb()])
    _patch(monkeypatch, bridge)
    result = runner.invoke(cli.app, ["debloat", "-s", "S1"], input="y\ny\n")
    assert result.exit_code == 0

    log = ActionLog(path=tmp_path / "actions.jsonl")
    events = [e["event"] for e in log.read_entries()]
    for expected in ("consent_recorded", "plan_proposed", "plan_confirmed", "step_executed"):
        assert expected in events
    assert log.verify() is True


@pytest.mark.parametrize("mission", list(Mission))
def test_every_mission_value_is_runnable_argument(mission):
    # Each mission is a valid CLI argument value (guards enum/CLI drift).
    assert mission.value in {"audit", "optimize", "flash", "unlock"}
