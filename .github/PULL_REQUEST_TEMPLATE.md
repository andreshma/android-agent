<!-- Thanks for contributing! Keep PRs focused and small where possible. -->

## What & why

<!-- What does this change and why? Link any issue: Closes #123 -->

## Type

- [ ] feat
- [ ] fix
- [ ] docs
- [ ] refactor / chore

## Safety checklist (required)

- [ ] I did **not** add anything that bypasses locks/FRP/carrier locks or
      targets a device the operator doesn't own.
- [ ] Any new device command is added to `bridge/allowlist.py` **on purpose**
      (I did not route around the bridge or allowlist).
- [ ] Destructive steps are marked `RiskLevel.HIGH` and `reversible=False`.
- [ ] Capabilities still call `require_authorized()` before executing.

## Tests

- [ ] Added/updated tests (required for allowlist, consent, or parsing changes).
- [ ] `ruff check .` and `pytest` pass locally on my OS.
