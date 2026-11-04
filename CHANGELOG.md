# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
- **Allowlist now validates arguments, not just the sub-command** (audit H1):
  per-key argument validators (regex per position, fail-closed) plus an expanded
  shell-metacharacter check, closing device-side `adb shell` injection like
  `getprop ro.x $(reboot)`.
- **Serial is always forced** (audit H2): `with_serial` strips any supplied
  `-s <serial>` and injects the authorized one, so a plan can't target another
  connected device.
- **`cmd package` restricted** (audit H3): only `cmd package list packages` is
  allowed; `uninstall`/`install-existing` are denied. `adb backup` removed
  (unused; `-f <path>` was a host-file-overwrite vector).
- **Flash safety** (audit H4/H5): a failed state-changing step stops the rest of
  the sequence; ROM-flash checks every image file exists; `fastboot flash` and
  bootloader unlock have no timeout (killing a write mid-flight bricks).
- **Mission-scope + protected packages** (audit M4): a proposed plan is rejected
  if a step is outside its mission's allowed commands, or disables/clears a
  protected core package.
- **Option-injection guard**: partition/image values starting with `-` are
  rejected (red-team scenario 6).
- Security docs reworded to match verified behaviour (audit M7); the self-run
  adversarial review corrected where the audit proved it over-optimistic.
- **Tightened `dumpsys` allowlist**: replaced the blanket `shell:dumpsys` with
  specific read-only services (`dumpsys package`, `dumpsys batterystats`), so
  state-changing dumpsys sub-commands (e.g. `deviceidle`) are no longer allowed.
- **Device-mode guard**: each mission now requires the right connection mode
  (audit/optimize → adb, flash/unlock → fastboot); mismatches abort with a clear
  message before anything runs (`orchestrator.require_mode`).
- **Authoritative risk + plan validation**: proposed plans are re-validated
  against the allowlist and each step's risk is re-derived from its command
  (`allowlist.risk_for`, `orchestrator.annotate_plan_risk`) before the user
  confirms. The LLM can no longer understate a step's risk, and a
  non-allowlisted command now rejects the whole plan at propose time.

### Added
- `python -m android_agent` entry point.
- 360° audit report + CycloneDX SBOM under `audits/`.
- `--runner` is now an Enum validated by Typer and honours `ANDROID_AGENT_RUNNER`
  (audit M1); documented Ollama host/model config now reaches the backend
  (audit M2); `ANDROID_AGENT_ANTHROPIC_MODEL` added.
- Tracebacks no longer render locals (could leak an API key).
- `uv.lock` for reproducible installs (`uv sync --all-extras`).
- CLI-level tests (`typer.testing.CliRunner`) covering the consent → confirm →
  execute flow, mode guard, and consent decline.
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
