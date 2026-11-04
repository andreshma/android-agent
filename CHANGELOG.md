# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Battery drain analysis** in optimize: ranks the top power-consuming apps by
  joining `dumpsys batterystats` estimated power use with a uid→package map
  (`battery.top_power_consumers`), surfaced in the optimize facts.
- **docs/TESTING.md**: manual on-device test checklist (read-only → reversible →
  destructive), complementing the automated suite.
- CI now runs **mypy as a blocking step** (the codebase is type-clean).
- **`debloat` command**: deterministic (no-LLM) detection of likely-bloatware
  apps (OEM/carrier/preinstalled bundles) and a reversible plan that disables
  them; core/system apps are protected from being flagged.
- **`flash-rom` command**: a verified, ordered, guarded ROM-flash walkthrough
  (`FlashCapability.build_rom_flash_plan`) — verifies the target, flashes
  partitions in a recommended order, then reboots.
- **`log` command**: review the recorded action trail, optionally filtered by
  device serial (`ActionLog.read_entries`).
- `Orchestrator` now accepts `llm=None` for deterministic plans that need no
  model.
- **Container sandbox** (`ContainerRunner`, `--runner container`): runs the
  toolchain in a network-less Podman/Docker container — USB passthrough on
  Linux, host adb server over the Docker gateway on Windows/macOS. Includes
  `docker/adb-tools.Dockerfile`.
- **Strict flash target verification**: `fastboot getvar product` is checked
  against the image's declared target before flashing; refuses (fail-safe) when
  the product can't be confirmed, to avoid bricking the wrong model.
- **Audit permission scan**: flags third-party apps holding granted
  privacy-sensitive permissions (microphone, camera, location, contacts, SMS,
  call log, …) by parsing `dumpsys package`.
- **Append-only action log** (JSONL): records proposed plans and executed steps
  per device, closing the repudiation gap in the threat model. On by default;
  `--no-log` to disable, `ANDROID_AGENT_LOG` to relocate.
- Project scaffold: layered (ports & adapters) architecture.
- Security boundary: `argv` command allowlist + ownership/consent gate.
- Two-phase flow: propose → confirm (extra yes for HIGH risk) → execute, with
  `--drill-down` to raw commands.
- Device discovery (`adb devices -l` / `fastboot devices`) and per-serial
  injection of the authorized target.
- Dual LLM backends behind one port: Ollama (local, default) and Claude
  (hosted), both via a shared structured-output `Plan` schema.
- Four capabilities (audit, optimize, flash, unlock) plus shared inspect.
- Cross-platform tool resolution (Windows `.exe` via `PATHEXT`, Linux PATH; env
  overrides).
- Community health, CI (Windows + Linux matrix), architecture docs, ADRs, threat
  model, security policy.
- Test suite (allowlist, consent, parsers, serial injection, schema).

### Known gaps / TODO
- No real-device integration test yet (see docs/TESTING.md for the manual
  checklist); unit tests use fake bridges.
- `ContainerRunner` image must be built/trusted by the operator.

[Unreleased]: https://github.com/andreshma/android-agent/commits/main
