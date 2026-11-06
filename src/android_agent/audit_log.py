"""Append-only, hash-chained action log.

Records what the agent *proposed* and what it actually *executed*, as one JSON
object per line (JSONL). This closes the repudiation gap in the threat model:
after the fact you can see exactly which commands ran against which device and
whether they succeeded.

Design notes:
  • Append-only JSONL — easy to tail, grep, and ship elsewhere; never rewritten.
  • Tamper-evident — each entry carries ``prev`` (the previous entry's hash) and
    its own ``hash`` over (prev + the entry's content). Deleting or editing a
    middle entry breaks the chain, which ``verify()`` detects (audit L4). This
    is integrity evidence, not secrecy: anyone who can rewrite the whole file
    can recompute the chain, so ship it somewhere append-only for real
    non-repudiation.
  • Best-effort — logging must never crash or block a device operation, so every
    write is wrapped and failures are swallowed (the run is what matters).
  • Default location is the per-user log dir (platformdirs), so it works the
    same on Windows and Linux; override with ``ANDROID_AGENT_LOG``.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from platformdirs import user_log_dir

from .models import Plan, StepResult

# The chain's root: the ``prev`` of the very first entry.
GENESIS_HASH = "0" * 64


def default_log_path() -> Path:
    override = os.environ.get("ANDROID_AGENT_LOG")
    if override:
        return Path(override)
    return Path(user_log_dir("android-agent", appauthor=False)) / "actions.jsonl"


def _entry_hash(prev: str, event: dict) -> str:
    """sha256 over the previous hash plus this entry's content (sans ``hash``)."""
    material = {k: v for k, v in event.items() if k != "hash"}
    payload = prev + json.dumps(material, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ActionLog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_log_path()
        self._last_hash: str | None = None

    def _read_last_hash(self) -> str:
        """The hash of the last well-formed entry, or GENESIS if none/unreadable."""
        last = GENESIS_HASH
        try:
            with self.path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    h = obj.get("hash")
                    if isinstance(h, str):
                        last = h
        except OSError:
            pass
        return last

    def _write(self, event: dict) -> None:
        event["ts"] = datetime.now(timezone.utc).isoformat()
        try:
            prev = self._last_hash if self._last_hash is not None else self._read_last_hash()
            event["prev"] = prev
            event["hash"] = _entry_hash(prev, event)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            is_new = not self.path.exists()
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
            if is_new:
                # Owner-only: the trail records serials and commands, so keep it
                # off other local users' eyes (best-effort; a no-op on Windows
                # ACLs) — audit L1.
                try:
                    os.chmod(self.path, 0o600)
                except OSError:
                    pass
            self._last_hash = event["hash"]
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

    def consent_recorded(self, serial: str) -> None:
        """Record that the operator passed the ownership/consent gate."""
        self._write({"event": "consent_recorded", "serial": serial})

    def plan_confirmed(self, serial: str, plan: Plan) -> None:
        """Record that the operator confirmed a plan and it is about to run."""
        self._write(
            {
                "event": "plan_confirmed",
                "serial": serial,
                "mission": plan.mission.value,
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

    def read_entries(self, serial: str | None = None) -> Iterator[dict]:
        """Yield logged events in order, optionally filtered by device serial.

        Malformed lines are skipped so a partially-written tail never breaks a
        read. Returns nothing if the log doesn't exist yet.
        """
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if serial is None or event.get("serial") == serial:
                    yield event

    def verify(self) -> bool:
        """Return True iff the hash chain is intact from genesis to the tail.

        A missing file is a valid (empty) chain. Any reordered, edited or
        removed entry breaks the ``prev``/``hash`` linkage and returns False.
        """
        prev = GENESIS_HASH
        if not self.path.exists():
            return True
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    return False
                if event.get("prev") != prev:
                    return False
                if event.get("hash") != _entry_hash(prev, event):
                    return False
                prev = event["hash"]
        return True
