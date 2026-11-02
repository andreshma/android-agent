# Security Policy

android-agent operates on physical Android devices over `adb`/`fastboot` and can
run destructive operations (flashing, bootloader unlock). Security is a
first-class concern, not an add-on. This document explains the model, the scope
boundary, and how to report a vulnerability.

## Scope boundary (by design)

android-agent is **only** for a device the operator owns and has physically
connected, after an explicit consent acknowledgement.

It does **not**, and will not, help:

- bypass a lock screen, PIN, pattern or biometric,
- bypass Factory Reset Protection (FRP) or a Google/manufacturer account lock,
- defeat carrier/SIM locks,
- operate on a device the operator does not own or is not authorized to modify.

PRs or feature requests in those directions are out of scope and will be
declined. Legitimate power-user operations on your own hardware (debloat, audit,
flash a custom ROM, unlock your own bootloader with OEM-unlock enabled) are
exactly what the project is for.

## Security model

Two mechanisms carry the weight:

1. **Command allowlist (`bridge/allowlist.py`).** The LLM never causes arbitrary
   shell to run. Every action is an `argv` list (never a shell string) validated
   against an explicit per-tool allowlist before the bridge executes it. Shell
   metacharacters are rejected. This also neutralizes prompt injection arriving
   *from the device itself* (e.g. a malicious app name in `pm list`): injected
   text can at worst ask for a command that isn't on the allowlist, which is
   denied.
2. **Consent / ownership gate (`consent.py`).** Capabilities call
   `require_authorized()` before executing anything; a device is only authorized
   after an interactive acknowledgement. The authorized serial is injected into
   every command so an action can only ever hit that one device.

On top of that: a two-phase *propose → confirm → execute* flow, an extra
explicit confirmation for HIGH-risk steps, and an optional network-less
container sandbox for the toolchain.

See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) for the full STRIDE analysis.

## Reporting a vulnerability

**Please do not open a public issue for security vulnerabilities.**

Use GitHub's **private vulnerability reporting** ("Report a vulnerability" under
the Security tab), or email the maintainers listed in the repository.

Please include:

- affected version / commit,
- a description of the issue and its impact,
- reproduction steps or a proof of concept (describe the *class* of problem;
  do not include a weaponized exploit).

We aim to acknowledge within **5 business days** and to agree on a disclosure
timeline with you. We support coordinated disclosure and will credit reporters
who wish to be named.

## Supported versions

While pre-1.0, only the latest `main` receives security fixes.
