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
[CHANGELOG.md](CHANGELOG.md). Good candidates:

- Harden `ContainerRunner` (drop capabilities, non-root `USER`, pin the base
  image by digest, read-only image mount) — audit M3.
- Add `pytest-cov` with a coverage floor, plus tests for the LLM adapters
  (`httpx.MockTransport` / a mocked Anthropic client) — audit M8.
- CI supply-chain jobs: SHA-pin actions, Dependabot cooldown, `uv sync
  --frozen`, a secret/SAST/SBOM job — audit M9.
- Wrap device facts in a delimited "data, not instructions" block and cap their
  size before sending to the LLM — audit M6.

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
