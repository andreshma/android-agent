"""End-to-end CLI tests driving the consent -> confirm -> execute flow with a
fake bridge, so the command wiring itself is covered (not just the pieces)."""

from typer.testing import CliRunner

from android_agent import cli
from android_agent.audit_log import ActionLog
from android_agent.bridge.sandbox import RunOutput
from android_agent.config import Config
from android_agent.models import Device, DeviceMode

runner = CliRunner()


class _FakeBridge:
    """Canned responses keyed by a recognizable token in the command."""

    def __init__(self, device: Device | None):
        self._device = device

    def find_device(self, serial: str):
        return self._device

    def read_property(self, device, prop: str):
        return {"ro.product.model": "FakePixel", "ro.build.version.release": "14"}.get(prop)

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


class _FakeLLM:
    """A stand-in LLM that returns a fixed, allowlisted audit plan."""

    name = "fake"

    def propose_plan(self, *, mission, request, device_facts):
        from android_agent.models import Plan, RiskLevel, Step

        return Plan(
            mission=mission,
            summary="Read one system property.",
            steps=[
                Step(
                    capability="audit",
                    human="Read the Android version",
                    command=["adb", "shell", "getprop", "ro.build.version.release"],
                    risk=RiskLevel.NONE,
                )
            ],
        )

    def explain(self, text):  # pragma: no cover - not exercised here
        return text


def test_devices_none(monkeypatch):
    _patch_bridge(monkeypatch, None)
    # list_devices isn't on the fake; devices command calls it, so give it one.
    monkeypatch.setattr(_FakeBridge, "list_devices", lambda self: [], raising=False)
    result = runner.invoke(cli.app, ["devices"])
    assert result.exit_code == 0
    assert "No devices detected" in result.stdout


def test_devices_lists_found(monkeypatch):
    device = Device(serial="S1", mode=DeviceMode.ADB, model="Pixel_7")
    _patch_bridge(monkeypatch, device)
    monkeypatch.setattr(_FakeBridge, "list_devices", lambda self: [device], raising=False)
    result = runner.invoke(cli.app, ["devices"])
    assert result.exit_code == 0
    assert "S1" in result.stdout
    assert "Pixel_7" in result.stdout


def test_log_renders_recorded_entries(monkeypatch, tmp_path):
    p = tmp_path / "actions.jsonl"
    monkeypatch.setenv("ANDROID_AGENT_LOG", str(p))
    from android_agent.audit_log import ActionLog
    from android_agent.models import Mission, Plan, RiskLevel, Step, StepResult

    log = ActionLog(path=p)
    plan = Plan(
        mission=Mission.OPTIMIZE,
        summary="x",
        steps=[
            Step(
                capability="optimize", human="h", command=["adb", "shell", "x"], risk=RiskLevel.LOW
            )
        ],
    )
    log.consent_recorded("S1")
    log.plan_proposed("S1", plan)
    log.plan_confirmed("S1", plan)
    log.step_executed("S1", StepResult(step=plan.steps[0], ok=True))

    result = runner.invoke(cli.app, ["log", "-s", "S1"])
    assert result.exit_code == 0
    assert "Action log" in result.stdout
    assert "optimize" in result.stdout


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


def test_egress_disclosure_shown_for_hosted_backend(capsys):
    cli._disclose_egress(Config(llm_backend="anthropic"))
    out = capsys.readouterr().out
    assert "Data leaves your machine" in out
    assert "anthropic" in out


def test_egress_disclosure_silent_for_local_backend(capsys):
    cli._disclose_egress(Config(llm_backend="ollama"))
    assert capsys.readouterr().out.strip() == ""


def test_egress_disclosure_shown_for_remote_ollama(capsys):
    # Ollama is "local" only if its host is loopback; a remote host still sends
    # device data off-machine and must be disclosed (audit M9).
    cli._disclose_egress(Config(llm_backend="ollama", ollama_host="http://10.0.0.5:11434"))
    out = capsys.readouterr().out
    assert "Data leaves your machine" in out
    assert "10.0.0.5" in out


def test_show_plan_escapes_markup_in_untrusted_text(capsys):
    # A step description / command containing Rich markup must not be
    # interpreted (it would drop text or crash the renderer) — audit M3.
    from android_agent.models import Mission, Plan, RiskLevel, Step

    plan = Plan(
        mission=Mission.AUDIT,
        summary="summary [/oops] end",
        steps=[
            Step(
                capability="audit",
                human="Failure [DELETE_FAILED] here",
                command=["adb", "shell", "getprop", "ro.x"],
                risk=RiskLevel.NONE,
            )
        ],
    )
    cli._show_plan(plan)  # must not raise MarkupError
    out = capsys.readouterr().out
    assert "[DELETE_FAILED]" in out  # bracketed token is preserved, not swallowed
    assert "[/oops]" in out


def test_version_flag(capsys):
    result = runner.invoke(cli.app, ["--version"])
    assert result.exit_code == 0
    assert "android-agent" in result.stdout


def test_log_verify_ok_and_failure(monkeypatch, tmp_path):
    from android_agent.audit_log import ActionLog

    p = tmp_path / "actions.jsonl"
    monkeypatch.setenv("ANDROID_AGENT_LOG", str(p))
    log = ActionLog(path=p)
    log.consent_recorded("S1")
    log.plan_proposed("S1", _plan_cli())

    ok = runner.invoke(cli.app, ["log", "--verify"])
    assert ok.exit_code == 0
    assert "OK" in ok.stdout

    # Tamper with the first entry so the chain breaks.
    lines = p.read_text(encoding="utf-8").splitlines()
    import json as _json

    first = _json.loads(lines[0])
    first["serial"] = "HACKED"
    lines[0] = _json.dumps(first, ensure_ascii=False)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")

    bad = runner.invoke(cli.app, ["log", "--verify"])
    assert bad.exit_code == 1
    assert "FAILED" in bad.stdout


def _plan_cli():
    from android_agent.models import Mission, Plan, RiskLevel, Step

    return Plan(
        mission=Mission.OPTIMIZE,
        summary="x",
        steps=[
            Step(
                capability="optimize",
                human="h",
                command=["adb", "shell", "pm", "disable-user", "com.x"],
                risk=RiskLevel.LOW,
            )
        ],
    )


def test_run_audit_happy_path(monkeypatch):
    device = Device(serial="S1", mode=DeviceMode.ADB)
    _patch_bridge(monkeypatch, device)
    monkeypatch.setattr(cli, "make_llm", lambda backend, **kw: _FakeLLM())
    result = runner.invoke(
        cli.app, ["run", "audit", "check version", "-s", "S1", "--no-log"], input="y\ny\n"
    )
    assert result.exit_code == 0, result.stdout
    assert "Read the Android version" in result.stdout
    assert "ok" in result.stdout


def test_run_rejects_offmission_plan(monkeypatch):
    # An audit plan carrying a flash step must be rejected at propose time.
    device = Device(serial="S1", mode=DeviceMode.ADB)
    _patch_bridge(monkeypatch, device)

    class _BadLLM(_FakeLLM):
        def propose_plan(self, *, mission, request, device_facts):
            from android_agent.models import Plan, RiskLevel, Step

            return Plan(
                mission=mission,
                summary="sneaky",
                steps=[
                    Step(
                        capability="audit",
                        human="Wipe it",
                        command=["fastboot", "flash", "system", "evil.img"],
                        risk=RiskLevel.NONE,
                    )
                ],
            )

    monkeypatch.setattr(cli, "make_llm", lambda backend, **kw: _BadLLM())
    result = runner.invoke(cli.app, ["run", "audit", "do it", "-s", "S1", "--no-log"], input="y\n")
    assert result.exit_code != 0
    assert "Rejected" in result.stdout


def test_debloat_logs_full_trail(monkeypatch, tmp_path):
    # consent -> plan_proposed -> plan_confirmed -> step_executed, hash-chained.
    monkeypatch.setenv("ANDROID_AGENT_LOG", str(tmp_path / "actions.jsonl"))
    device = Device(serial="S1", mode=DeviceMode.ADB)
    _patch_bridge(monkeypatch, device)
    result = runner.invoke(cli.app, ["debloat", "-s", "S1"], input="y\ny\n")
    assert result.exit_code == 0

    log = ActionLog(path=tmp_path / "actions.jsonl")
    events = [e["event"] for e in log.read_entries()]
    assert "consent_recorded" in events
    assert "plan_proposed" in events
    assert "plan_confirmed" in events
    assert "step_executed" in events
    assert log.verify() is True
