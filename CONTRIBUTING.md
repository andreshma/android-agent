# Contributing to android-agent

Thanks for helping! This project is a safety-first agent for people's own
Android devices, so a few principles are non-negotiable — everything else is
open to discussion.

## Ground rules

1. **Own-device scope only.** Never add anything that bypasses lock screens,
   FRP, carrier locks, or the security of a device the operator doesn't own. PRs
   in that direction will be declined. Legitimate power-user operations on your
   own hardware (debloat, audit, flash a custom ROM, unlock your own bootloader)
   are exactly what this project is for.
2. **The LLM never runs shell.** All execution goes through
   `bridge.device.Bridge`, which validates every `argv` command against
   `bridge.allowlist`. If a feature needs a new command, add it to the allowlist
   *on purpose* with a comment — don't route around the boundary.
3. **Two-phase contract.** New capabilities propose a `Plan`; they don't act
   without confirmation. Mark destructive steps `RiskLevel.HIGH` and set
   `reversible=False`.
4. **Keep the consent gate.** Capabilities call `require_authorized()` before
   executing. Don't skip it.

## Good first contributions

See the open items in the latest [`audits/`](audits/) report and
[CHANGELOG.md](CHANGELOG.md). The High findings and all tracked Medium/Low
items are now addressed; good remaining candidates:

- **Container image flashing**: let `ContainerRunner` mount the image directory
  read-only so `flash-rom` works in container mode, not just the read-only
  missions (today it's host-runner only — see the threat model).
- **Real-device integration test**: automate the manual checklist in
  [docs/TESTING.md] against a device or an emulator in CI.
- **Pin the base image by digest** in `docker/adb-tools.Dockerfile` and wire a
  container image scan (Trivy/Grype) into the `security` CI job.
- **Harden the allowlist argument validators** further with property-based
  (Hypothesis) tests for the regexes.

## Dev setup

```bash
pip install -e ".[dev,anthropic]"
ruff check .
mypy src
pytest
```

For a reproducible environment, use the committed lockfile with
[uv](https://docs.astral.sh/uv/):

```bash
uv sync --all-extras   # installs the exact versions from uv.lock
```

`pyproject.toml` stays the source of truth for dependency ranges; `uv.lock` pins
the exact resolved versions. Regenerate it with `uv lock` after changing deps.

## Commit style

Conventional Commits (`feat:`, `fix:`, `docs:`…). Add a test for anything that
touches the allowlist or the consent gate.
