# 0002. Ownership / consent gate and own-device scope

- Status: Accepted
- Date: 2026-11-02

## Context and problem statement

The tool can erase data and unlock bootloaders. It must be unambiguous — in code
and to the operator — that it acts only on a device the operator owns and
consents to modify, and never helps bypass security on someone else's device.

## Decision drivers

- Ethical and legal scope: own-device only.
- The boundary must be enforced, not merely documented.
- Destructive missions must not run against an un-cleared device.

## Considered options

- **A. First-class consent gate** (`consent.py`) plus per-serial authorization,
  enforced in the capability base before any execution.
- **B. A disclaimer in the README** and nothing in code.

## Decision

Option **A**. An interactive consent acknowledgement marks a `Device`
`authorized` for its serial; `require_authorized()` is called by every
capability before executing; the authorized serial is injected into every
command. Bypassing locks / FRP / carrier locks / non-owned devices is explicitly
out of scope and refused.

## Consequences

- Positive: scope is enforced at the chokepoint and is testable.
- Positive: pairs with the serial injection so actions can't hit another device.
- Negative: an extra interactive step (intended) before any run.
