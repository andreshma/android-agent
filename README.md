# android-agent

![CI](https://github.com/andreshma/android-agent/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-Apache--2.0-green)
![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey)

An LLM-driven agent that helps you **audit, optimize, flash and unlock _your own_
Android device** — inside a sandbox, with clear human-language explanations, and
with your confirmation before anything changes.

It puts a local or hosted LLM between what you *want* ("my phone is slow", "I want
to install LineageOS", "which apps are spying on me?") and the technical
`adb`/`fastboot` commands — translating in both directions, and letting you
**drill down** to the exact command whenever you want to see it.

> ⚠️ **Scope.** android-agent operates only on a device you own and have
> physically connected, after you confirm an on-screen consent gate. It does
> **not** help bypass lock screens, Factory Reset Protection (FRP), carrier
> locks, or any security on a device you don't own. That is out of scope by
> design and the code refuses it.

## Why

Power-user Android maintenance (debloating, auditing permissions, flashing a
custom ROM, unlocking your bootloader) is powerful but intimidating and easy to
get wrong. android-agent makes it **explainable and safe-by-default**: read-only
first, reversible where possible, and a hard confirmation before anything
destructive.

## How it works

```
┌─ CLI (Typer) ────────────────────────────────────┐
│  Natural-language chat + optional --drill-down    │
├─ Orchestrator ───────────────────────────────────┤
│  intent → facts → LLM Plan → explain → confirm    │
├─ Capabilities (one per mission) ─────────────────┤
│  audit · optimize · flash · unlock  (+ inspect)   │
├─ Device bridge ──────────────────────────────────┤
│  adb/fastboot, ALLOWLIST, argv only (no shell)    │
├─ Sandbox runner ─────────────────────────────────┤
│  local  |  network-less container w/ USB passthru │
└───────────────────────────────────────────────────┘
```

Two principles make it safe:

1. **Two-phase contract.** The LLM never runs anything. It proposes a `Plan` of
   steps, each with a plain-language description and a risk level. You see the
   plan, optionally drill into the raw commands, and confirm. HIGH-risk plans
   need an extra explicit yes.
2. **Allowlist.** Every command is an `argv` list (never a shell string) checked
   against an explicit per-tool allowlist before the bridge runs it. The LLM
   cannot cause arbitrary shell to execute, which also neutralizes prompt
   injection coming from the device itself.

## The four missions

| Mission | What it does | Risk |
|---|---|---|
| **audit** | List apps, flag mic/camera/location grants, find bloatware. | None (read-only) |
| **optimize** | Disable bloatware (reversible), clear caches, review battery. | Low, reversible |
| **flash** | Guide a LineageOS/firmware flash with model checks + backup. | High |
| **unlock** | `fastboot flashing unlock` on *your own* device (erases data). | High |

## LLM backends

Pick either, swap freely — same interface:

- **Ollama (local, default).** Your device's data never leaves the machine.
- **Claude API (hosted).** More capable planning; `pip install android-agent[anthropic]`
  and set `ANTHROPIC_API_KEY`.

## Status

Early alpha. The architecture, the security boundary (allowlist + consent gate),
the two-phase flow, device discovery, and the end-to-end CLI run are in place and
tested (19 tests). Working today:

- ✅ device discovery — parses `adb devices -l` / `fastboot devices`
- ✅ structured `propose_plan` for both backends (Ollama JSON mode, Claude tool use)
- ✅ end-to-end CLI: consent → plan → drill-down → confirm → execute
- ✅ serial injection so an action can only ever hit the authorized device
- ✅ audit permission scan — flags apps with mic/camera/location/… granted
- ✅ append-only action log (audit trail), on by default

Deliberate, clearly-marked stubs left for the community (`TODO(contributors)`):

- `bridge.sandbox.ContainerRunner` — Podman/Docker with USB passthrough, no net
- strict model/variant verification in `capabilities.flash`

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Requirements

- Python 3.10+
- Android **platform-tools** (`adb`, `fastboot`) on your `PATH`.
  Override the paths with `ANDROID_AGENT_ADB` / `ANDROID_AGENT_FASTBOOT` if they
  live elsewhere.
- (optional) a local **Ollama** server, or an `ANTHROPIC_API_KEY` for Claude.

### Cross-platform notes (Windows & Linux)

Tool lookup uses `shutil.which`, so on **Windows** `adb` resolves to `adb.exe`
via `PATHEXT` automatically, and on **Linux/macOS** it uses the normal PATH — no
per-OS config needed. The optional container sandbox passes USB through directly
on Linux (`--device=/dev/bus/usb`); on Windows/macOS it points a network-less
container's adb at the host adb server over loopback (see `ContainerRunner`).

## Install (dev)

```bash
pip install -e ".[dev,anthropic]"
pytest
android-agent --help
android-agent devices
android-agent run audit "which apps can use my microphone?" -s <SERIAL> --drill-down
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — layers, C4 views, patterns, invariants
- [Architecture Decision Records](docs/adr/README.md)
- [Threat model](docs/THREAT_MODEL.md) — STRIDE analysis
- [Security policy](SECURITY.md) — scope boundary & how to report issues
- [Contributing](CONTRIBUTING.md) · [Code of Conduct](CODE_OF_CONDUCT.md) ·
  [Changelog](CHANGELOG.md)

## License

Apache-2.0. See [LICENSE](LICENSE).

> Flashing firmware and unlocking a bootloader can erase your data and void your
> warranty. You run this on your own hardware, at your own risk.
