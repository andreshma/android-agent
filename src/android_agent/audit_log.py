"""Append-only action log.

Records what the agent *proposed* and what it actually *executed*, as one JSON
object per line (JSONL). This closes the repudiation gap in the threat model:
after the fact you can see exactly which commands ran against which device and
whether they succeeded.

Design notes:
  • Append-only JSONL — easy to tail, grep, and ship elsewhere; never rewritten.
  • Best-effort — logging must never crash or block a device operation, so every
    write is wrapped and failures are swallowed (the run is what matters).
  • Default location is the per-user log dir (platformdirs), so it works the
    same on Windows and Linux; override with ``ANDROID_AGENT_LOG``.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from platformdirs import user_log_dir

from .models import Plan, StepResult


def default_log_path() -> Path:
    override = os.environ.get("ANDROID_AGENT_LOG")
    if override:
        return Path(override)
    return Path(user_log_dir("android-agent", appauthor=False)) / "actions.jsonl"


class ActionLog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_log_path()

    def _write(self, event: dict) -> None:
        event["ts"] = datetime.now(timezone.utc).isoformat()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError:
            # Best-effort: never let logging break a device operation.
            pass

    def plan_proposed(self, serial: str, plan: Plan) -> None:
        self._write(
            {
                "event": "plan_proposed",
                "serial": serial,
                "mission": plan.mission.value,
                "summary": plan.summary,
                "steps": len(plan.steps),
                "max_risk": plan.max_risk.value,
            }
        )

    def step_executed(self, serial: str, result: StepResult) -> None:
        self._write(
            {
                "event": "step_executed",
                "serial": serial,
                "capability": result.step.capability,
                "command": result.step.command,
                "risk": result.step.risk.value,
                "ok": result.ok,
                "error": result.error.strip() or None,
            }
        )
