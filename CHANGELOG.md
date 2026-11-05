# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Real-subprocess flash integration test** (`tests/test_flash_integration.py`):
  drives the full `flash-rom` flow through the **real execution path** — an
  executable `adb`/`fastboot` stub pointed to by the env overrides, so
  `LocalRunner` actually spawns a process and the real parsers handle its output
  (device discovery, the live `getvar product` target check, the ordered
  partition flash, the reboot, and the wrong-target refusal). It validates the
  flow over real process I/O — the gap between the fake-bridge e2e tests (which
  stop at the Python boundary) and a physical device (which an emulator can't
  stand in for, having no fastboot mode). POSIX-only; skipped on Windows, where
  image-path handling is covered by the allowlist unit tests.

## [0.1.2] - 2026-11-04

Live-validation hardening, honest capability/limitation and validation docs, a
model-choice note, the Examples Cookbook, plus release-to-PyPI and real-emulator
CI automation.

### Changed
- **Live LLM validation hardening.** Validating the `run` missions against a
  real device (emulator) with both Ollama and Claude surfaced two rough edges,
  now fixed: the audit mission allowlists read-only `pm list permissions`
  (`-g/-f/-d/-u/-s`, risk NONE) — a command real models naturally propose for a
  permission audit — and the plan schema now states each `command` MUST start
  with `adb`/`fastboot` (a smaller model had omitted the prefix). The security
  boundary is unchanged otherwise: the additions are read-only and on-mission.

### Added
- **Capabilities & limitations made explicit** ([docs/USAGE.md](docs/USAGE.md)
  §1.1, README): a "what it does **not** do" section — no backup creation, no
  app install/uninstall (optimize only disables, reversibly), no OTA/recovery
  sideload (fastboot partition images only), no factory-wipe/erase, no
  diagnostics, no lock-screen/FRP/carrier-lock bypass — so expectations stay
  honest.
- **Model-choice guidance** ([docs/USAGE.md](docs/USAGE.md) §2.2, README):
  capable models follow the allowlisted-JSON plan contract reliably; very small
  models may produce a plan that is rejected before anything runs (a safe
  failure). Re-run or pick a stronger model.
- **Validation status table** ([docs/TESTING.md](docs/TESTING.md)): an honest
  per-area record of what was exercised live against the emulator (devices,
  audit with both backends, the debloat reversible cycle, the LLM round-trip,
  the allowlist guardrail) versus what remains hardware-only and unverified live
  by the maintainer (flash, unlock) or parser-tested but not run live (battery
  ranking, container runner).
- **Examples Cookbook** ([docs/EXAMPLES.md](docs/EXAMPLES.md)): copy-paste
  examples covering every feature — install, tool paths, both backends, each
  command and flag, the container runner, logging/verification, practising on an
  emulator, troubleshooting, and a full ROM-flash walkthrough — with real run
  transcripts and both bash and Windows PowerShell variants. Linked from the
  README and the User Manual.
- **PyPI publishing pipeline, opt-in** (`.github/workflows/release.yml`): a
  **manual** (`workflow_dispatch`) workflow that builds the sdist + wheel and
  publishes to PyPI via **Trusted Publishing** (OIDC — no API token stored in the
  repo), in a dedicated `pypi` environment. Publishing to PyPI is **deferred to a
  future phase** and never triggers automatically on a tag; installing from a
  clone (`pip install -e .`) remains the supported path. See
  [RELEASING.md](RELEASING.md) for the one-time setup and how to trigger it.
- **Real-emulator smoke test in CI** (`emulator-smoke` job): boots an Android
  emulator (`reactivecircus/android-emulator-runner`) and runs
  `scripts/emulator_smoke.py`, which exercises the bridge → parse → allowlist
  read path against **real adb I/O** — the one thing the fake-bridge unit tests
  cannot cover (closes the "no real-device integration test" gap).

## [0.1.1] - 2026-11-04

Documentation, legal, and test hardening on top of 0.1.0, plus a real
cross-platform flashing fix.

### Fixed
- **Cross-platform flashing**: the allowlist's blanket shell-metacharacter check
  rejected any token containing `\`, spaces or `()`, so a real Windows image
  path (`C:\…\boot.img`, `Program Files (x86)`) made `fastboot flash` fail with
  `CommandDenied`. The metacharacter guard is now scoped to `adb shell`
  arguments (the only place the device re-parses them); host-side `fastboot`
  image paths run with `shell=False` and accept normal path characters, still
  rejecting option-injection (leading `-`) and control characters.

### Added
- **User Manual** ([docs/USAGE.md](docs/USAGE.md)): dependencies, device setup,
  every command and flow, and the full flashing/unlock workflow.
- **Disclaimer & liability waiver** ([DISCLAIMER.md](DISCLAIMER.md)): no warranty,
  use-at-your-own-risk, your responsibilities, and limitation of liability,
  linked prominently from the README.
- **End-to-end flow tests** (`tests/test_flows_e2e.py`): every user flow —
  devices, audit, optimize, debloat, flash-rom, unlock, the guard rails
  (consent decline, wrong mode, off-mission rejection, stop-on-failure,
  HIGH-risk typed-yes), hosted-backend egress and the verifiable log — emulated
  through the real CLI with a fake bridge/LLM. Coverage now 85%.

## [0.1.0] - 2026-11-04

First public alpha. Full own-device agent (audit, optimize, debloat, flash-rom,
unlock) behind the two-phase propose→confirm→execute contract, dual LLM backends
(Ollama local / Claude hosted), the allowlist + consent security boundary, the
hardened container sandbox, and the 360° audit with every High/Medium/Low
finding remediated.

### Security
- **Container sandbox hardened** (audit M3): every `ContainerRunner` run now
  adds `--cap-drop=ALL`, `--security-opt=no-new-privileges`, a read-only root
  filesystem with a `/tmp` tmpfs, and PID/memory limits; the image runs as a
  non-root user. ROM images named in a command are bind-mounted read-only and
  their paths rewritten, so `flash-rom` works in the container on Linux.
- **Untrusted device data is framed and bounded** (audit M6): device facts are
  wrapped in a delimited `<device_facts>` block, labelled "data, not
  instructions" in both prompts, and capped at `schema.MAX_FACTS_CHARS`,
  reducing the prompt-injection surface from an app label or property.
- **Hosted-LLM egress is disclosed** (audit M6): selecting `--llm anthropic`
  now shows an explicit notice that device facts will be sent to a third-party
  API before any planning happens.
- **Action log is tamper-evident** (audit L4): entries are hash-chained
  (`prev`/`hash`), so an edited, reordered or deleted entry is detectable via
  `ActionLog.verify`. The log now also records the consent acknowledgement and
  the explicit plan confirmation, and `debloat`/`flash-rom` plans are logged.
- **LLM API key no longer leaks to the toolchain** (audit L3): the adb/fastboot
  child process is launched with a scrubbed environment that omits
  `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`; on Windows, a tool resolved from the
  current working directory is rejected (CWD-shadowing guard).
- **Destructive confirmation requires a typed "yes"** (audit L5): the HIGH-risk
  gate now rejects a bare `y`, so a piped `yes |` cannot auto-approve a flash.
- **Model/network errors are handled** (audit L2): an unreachable backend,
  malformed output or a `max_tokens`-truncated plan now abort with a clear
  message instead of a traceback; a truncated hosted-model plan is rejected
  rather than run partially (audit L7).
- **`fastboot devices` parsing tightened** (audit L7): only lines whose second
  field is `fastboot` are treated as devices, so informational chatter is never
  mistaken for a serial.
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
- **Coverage floor in CI** (audit M8): `pytest-cov` with an 80% `fail_under`
  gate, plus tests for both LLM adapters (Ollama via a fake `httpx.post`,
  Anthropic via an injected client), the sandbox hardening/env-scrub, the
  hash-chained log, and the `run`/`devices`/`log` CLI paths.
- **CI supply-chain hardening** (audit M9): GitHub Actions pinned by commit SHA,
  a `uv sync --frozen` job that fails if `uv.lock` is stale, a `pip-audit` SCA
  job, Dependabot release cooldown, and the `anthropic` extra installed in CI so
  the hosted adapter is covered (audit L8).
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

[Unreleased]: https://github.com/andreshma/android-agent/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/andreshma/android-agent/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/andreshma/android-agent/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/andreshma/android-agent/releases/tag/v0.1.0
