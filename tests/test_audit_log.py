"""The action log is the audit trail, so verify it records what ran."""

import json

from android_agent.audit_log import ActionLog
from android_agent.models import Mission, Plan, RiskLevel, Step, StepResult


def _plan() -> Plan:
    return Plan(
        mission=Mission.OPTIMIZE,
        summary="Disable one app.",
        steps=[
            Step(
                capability="optimize",
                human="Disable the news app",
                command=["adb", "shell", "pm", "disable-user", "com.x.news"],
                risk=RiskLevel.LOW,
            )
        ],
    )


def test_chain_continues_across_separate_instances(tmp_path):
    # Each CLI invocation builds a fresh ActionLog; the chain must still link
    # across processes via _read_last_hash, and verify() must hold (audit M10).
    path = tmp_path / "actions.jsonl"
    first = ActionLog(path=path)
    first.consent_recorded("S1")
    first.plan_proposed("S1", _plan())

    # A brand-new instance (as a second `android-agent` run would create) must
    # pick up the previous tail hash, not restart from genesis.
    second = ActionLog(path=path)
    second.plan_confirmed("S1", _plan())
    second.step_executed("S1", StepResult(step=_plan().steps[0], ok=True))

    assert ActionLog(path=path).verify() is True
    lines = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 4
    # the second instance's first entry chains onto the first instance's tail
    assert lines[2]["prev"] == lines[1]["hash"]


def test_verify_detects_a_tampered_middle_entry(tmp_path):
    path = tmp_path / "actions.jsonl"
    log = ActionLog(path=path)
    log.consent_recorded("S1")
    log.plan_proposed("S1", _plan())
    log.step_executed("S1", StepResult(step=_plan().steps[0], ok=True))
    assert ActionLog(path=path).verify() is True

    lines = path.read_text(encoding="utf-8").splitlines()
    middle = json.loads(lines[1])
    middle["serial"] = "TAMPERED"  # edit content without fixing the hash
    lines[1] = json.dumps(middle, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert ActionLog(path=path).verify() is False


def test_log_writes_jsonl(tmp_path):
    log = ActionLog(path=tmp_path / "actions.jsonl")
    plan = _plan()
    log.plan_proposed("SERIAL1", plan)
    log.step_executed(
        "SERIAL1",
        StepResult(step=plan.steps[0], ok=True, output="Package disabled"),
    )

    lines = (tmp_path / "actions.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    proposed = json.loads(lines[0])
    assert proposed["event"] == "plan_proposed"
    assert proposed["mission"] == "optimize"
    assert proposed["max_risk"] == "low"
    assert "ts" in proposed

    executed = json.loads(lines[1])
    assert executed["event"] == "step_executed"
    assert executed["command"][-1] == "com.x.news"
    assert executed["ok"] is True


def test_log_appends(tmp_path):
    log = ActionLog(path=tmp_path / "a.jsonl")
    log.plan_proposed("S", _plan())
    log.plan_proposed("S", _plan())
    lines = (tmp_path / "a.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_log_is_best_effort_on_bad_path(tmp_path):
    # A path whose parent is a file (not a dir) can't be created; must not raise.
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    log = ActionLog(path=blocker / "nested" / "a.jsonl")
    log.plan_proposed("S", _plan())  # should silently no-op, not crash


def test_read_entries_filters_by_serial(tmp_path):
    log = ActionLog(path=tmp_path / "a.jsonl")
    log.plan_proposed("AAA", _plan())
    log.plan_proposed("BBB", _plan())
    log.step_executed("AAA", StepResult(step=_plan().steps[0], ok=True))
    all_entries = list(log.read_entries())
    assert len(all_entries) == 3
    aaa = list(log.read_entries(serial="AAA"))
    assert len(aaa) == 2
    assert all(e["serial"] == "AAA" for e in aaa)


def test_read_entries_skips_malformed_lines(tmp_path):
    p = tmp_path / "a.jsonl"
    p.write_text('{"event":"x","serial":"S"}\nnot json\n{"event":"y"}\n', encoding="utf-8")
    entries = list(ActionLog(path=p).read_entries())
    assert [e["event"] for e in entries] == ["x", "y"]


def test_read_entries_missing_file(tmp_path):
    assert list(ActionLog(path=tmp_path / "nope.jsonl").read_entries()) == []


def test_chain_verifies_intact(tmp_path):
    log = ActionLog(path=tmp_path / "a.jsonl")
    log.consent_recorded("S")
    log.plan_proposed("S", _plan())
    log.plan_confirmed("S", _plan())
    log.step_executed("S", StepResult(step=_plan().steps[0], ok=True))
    assert log.verify() is True
    # every entry links to the previous one's hash
    entries = list(log.read_entries())
    assert entries[0]["prev"] == "0" * 64
    assert all("hash" in e for e in entries)
    assert entries[1]["prev"] == entries[0]["hash"]


def test_chain_detects_tampering(tmp_path):
    p = tmp_path / "a.jsonl"
    log = ActionLog(path=p)
    log.plan_proposed("S", _plan())
    log.step_executed("S", StepResult(step=_plan().steps[0], ok=True))
    assert log.verify() is True

    # Edit a field of the first entry without recomputing the chain.
    lines = p.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["serial"] = "TAMPERED"
    lines[0] = json.dumps(first)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert ActionLog(path=p).verify() is False


def test_chain_detects_deletion(tmp_path):
    p = tmp_path / "a.jsonl"
    log = ActionLog(path=p)
    log.plan_proposed("S", _plan())
    log.plan_proposed("S", _plan())
    log.step_executed("S", StepResult(step=_plan().steps[0], ok=True))

    # Remove the middle entry: the chain's prev-links no longer line up.
    lines = p.read_text(encoding="utf-8").splitlines()
    del lines[1]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert ActionLog(path=p).verify() is False


def test_verify_empty_log_is_valid(tmp_path):
    assert ActionLog(path=tmp_path / "none.jsonl").verify() is True
