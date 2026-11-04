# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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
- `ContainerRunner` (network-less container, USB passthrough) — interface only.
- Strict model/variant verification before `fastboot flash`.

[Unreleased]: https://github.com/andreshma/android-agent/commits/main
