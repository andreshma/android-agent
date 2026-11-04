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
