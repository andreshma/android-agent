# 0001. Command allowlist as the security boundary

- Status: Accepted
- Date: 2026-11-02

## Context and problem statement

An LLM proposes the actions android-agent takes against a real device. LLM
output cannot be trusted to be safe or correct, and some device data (app names,
properties) is attacker-controllable and could carry prompt injection. We need a
hard guarantee that no arbitrary or destructive command can run just because the
model (or injected text) asked for it.

## Decision drivers

- The LLM output is untrusted by definition.
- Prompt injection can arrive from the device itself.
- A single, reviewable chokepoint beats scattered checks.

## Considered options

- **A. Allowlist of `argv` sub-commands**, validated at one bridge chokepoint.
- **B. Denylist** of known-dangerous commands.
- **C. Let the LLM emit shell**, review by prompt instructions only.

## Decision

Option **A**. Every action is an `argv` list (never a shell string) and must
match an explicit per-tool allowlist (`bridge/allowlist.py`) before the bridge
runs it. Shell metacharacters are rejected. Adding a capability means adding its
sub-commands to the allowlist on purpose.

## Consequences

- Positive: injected text can at worst request a denied command; no arbitrary
  shell; the boundary is small and unit-tested.
- Positive: `shell=False` everywhere removes word-splitting/interpretation.
- Negative: new features require an explicit allowlist edit (intended friction).
