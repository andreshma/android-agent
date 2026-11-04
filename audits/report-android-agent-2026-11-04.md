# Audit 360 report: android-agent

| Field | Value |
|---|---|
| Project | `android-agent` v0.1.0 (alpha), Apache-2.0 |
| Audit date | 2026-11-04 |
| Commit audited | `c6ac962` |
| Type | Advisory, pre-release (never blocks) |
| Tier assumed | MVP / open-source alpha |
| RAG | **AMBER** (no P0; 5 High, all fixable locally) |
| Findings | 0 Critical · 5 High · 9 Medium · 8 Low · 2 Info (24) |

> **Scope note.** The tool operates only on the operator's own device with
> consent and deliberately does not bypass locks/FRP/carrier locks. That scope
> is not a finding. Findings are about whether the code and docs *enforce* the
> stated boundaries.

## Remediation status (post-audit follow-up)

The High findings and several Mediums were fixed in the commit that follows this
report. Summary:

| ID | Finding | Status |
|---|---|---|
| H1 | Allowlist validated shape but not arguments (`$(...)`, backticks, `&`, `>`, `\n` passed `adb shell`) | **Fixed** — per-key argument validators + expanded metacharacter set |
| H2 | `with_serial` honored a supplied `-s OTHER` (wrong-device targeting) | **Fixed** — selector always stripped and replaced with the authorized serial |
| H3 | `shell:cmd package` blanket at risk NONE (allowed `uninstall`) | **Fixed** — restricted to `cmd package list packages` |
| H4 | Flash sequence continued after a failed step; no image-exists check | **Fixed** — stop-on-failure for state-changing steps; image existence checked |
| H5 | Fixed 120 s timeout killed `fastboot flash` mid-write | **Fixed** — per-key timeouts (flash/unlock: no timeout) |
| M1 | `--runner` failed open to `LocalRunner`; env var ignored | **Fixed** — Enum option + env var default |
| M2 | Ollama host/model from config never reached the backend | **Fixed** — passed through `make_llm` |
| M4 | LLM plans validated for shape, not meaning | **Partially fixed** — mission-scope enforcement + protected-package rejection + merge-order fix; argument/option checks centralized in the allowlist |
| M5 | "required backup step" documented but absent; `adb backup` arg-free | **Partially fixed** — `adb backup` removed from the allowlist; backup remains a documented precondition |
| M7 | Security docs claimed controls the code didn't provide | **Fixed** — docs reworded to match verified behaviour |
| L1, L6 | `.coverage` tracked; stale counts/docstrings | **Fixed** |
| M3 | Container sandbox weaker than documented | **Fixed** — cap-drop ALL, no-new-privileges, read-only root + tmpfs, PID/mem limits, non-root user, read-only image bind-mounts (flash works in-container on Linux) |
| M6 | Untrusted device data in prompt; hosted egress undisclosed | **Fixed** — delimited `<device_facts>` block + size cap + egress notice |
| M8 | Security-path test gaps; no coverage tooling | **Fixed** — `pytest-cov` 80% floor + LLM adapter/sandbox/log/CLI tests |
| M9 | CI/supply-chain gaps | **Fixed** — SHA-pinned actions, `uv --frozen` job, pip-audit, Dependabot cooldown |
| L2 | Tracebacks could leak key; model/net errors unhandled | **Fixed** — locals off + typed error handling |
| L3 | Child env inherits API key; Windows CWD `which` | **Fixed** — scrubbed child env + CWD-shadow guard |
| L4 | Log not tamper-evident; consent/confirm/debloat/flash unlogged | **Fixed** — hash chain + full trail |
| L5 | No TTY/typed-yes check on destructive confirm | **Fixed** — HIGH gate requires literal `yes` |
| L7 | `fastboot devices` loose parsing; truncation unchecked | **Fixed** — strict device lines + `max_tokens` rejection |
| L8 | `anthropic` extra untested; adapter 0% coverage | **Fixed** — adapter tests + installed in CI |

---

# Executive summary

The architecture is clean and well documented for an alpha: ports and adapters,
a single bridge chokepoint, `shell=False` everywhere, authoritative risk
derivation, a two-phase confirm flow, ADRs, a STRIDE model and a red-team
document. Lint, types, SCA and the secret scan are clean, and complexity is very
low.

The weak spot at audit time was the allowlist: it validated the *shape* of a
command (first tokens) but not its *arguments*, and several security claims in
the docs were contradicted by reproduced behaviour (section 5). Those are now
addressed (see Remediation status).

### Top 5 (as found)
1. **H1** — allowlist metacharacter check rejected only `;`, `&&`, `|`; `$(...)`,
   backticks, `&`, `>`, `<`, newline passed, and `adb shell` re-parses argv on
   the device. `adb shell getprop ro.x $(reboot)` validated at risk `none`.
2. **H2** — `with_serial` returned the command unchanged if `-s` appeared, so
   `adb -s OTHER …` ran on OTHER, breaking the per-serial consent invariant.
3. **H3** — `shell:cmd package` was a blanket prefix at risk NONE, so
   `cmd package uninstall` validated as a no-risk step.
4. **H4/H5** — a flash plan continued after a failed step, and a fixed 120 s
   timeout could kill `fastboot flash` mid-write — a brick risk on the headline
   mission.
5. **M1** — `--runner` fell back to the unsandboxed `LocalRunner` on any value
   other than exactly `container`, and the option default overwrote
   `ANDROID_AGENT_RUNNER`.

### Scanners
- **Ran:** ruff (0), mypy (0), Semgrep (5), Bandit (110; 108 are B101 in tests),
  Trivy fs (0 vulns, 0 secrets, 2 Dockerfile misconfigs), Trivy CycloneDX SBOM
  (46 components), jscpd (0.63% duplication), lizard (avg CCN 2.01, max 9),
  pytest+coverage (62 passed, 72%), git-history secret grep (no hits).
- **Not run:** gitleaks, trufflehog, Syft, Grype, osv-scanner, pip-audit (not
  installed / covered by Trivy); Checkov (installed but broken); SonarQube
  (creds present but no project key — upload not authorized).
- **N/A:** Spectral, ESLint, pa11y, cosign, mutation, contract, e2e, load, DAST.

---

## Findings

Tags: `[DET]` deterministic evidence · `[JUDG]` reviewer judgment · `[VERIFY]`
needs a device/environment.

### HIGH

**H1. Metacharacter filter incomplete; `adb shell` re-parses argv on device `[DET]`**
Only `;`, `&&`, `|` were rejected. `adb shell` joins arguments into one string
for the device `sh`, so `$(...)`, backticks, `&`, `>`, `<`, `\n` still act as
shell syntax on the phone; anything after an allowlisted prefix was accepted at
risk NONE. Blast radius: the adb-shell uid on the device, not the host.
*Fix:* validate arguments per key (regex per position, fail-closed); keep the
metacharacter check as a secondary guard.

**H2. Serial injection bypass `[DET]`**
`with_serial` returned the command untouched if `-s` was anywhere in it, and
`_match_key` skipped a leading `-s <value>`. `adb -s OTHER shell pm clear com.x`
validated and kept `OTHER`. The old `test_with_serial_is_idempotent` locked the
unsafe behaviour in.
*Fix:* strip any supplied selector and always inject the authorized serial.

**H3. `shell cmd package` blanket allowlist at risk NONE `[DET]`**
Every verb passed (`uninstall`, `install-existing`, …) as a no-confirmation
step, contradicting "we never uninstall".
*Fix:* allowlist only `cmd package list packages` (+ the H1 argument check).

**H4. Flash sequence continues after a failed step `[DET]`**
`Bridge.execute` returns `ok=False` rather than raising, and the loop moved on,
so a failed `flash boot` still let `system`/`reboot` run. `flash-rom` also never
checked image files exist. Brick risk on the headline mission.
*Fix:* stop at the first failed state-changing step; check `Path(image).is_file()`.

**H5. Fixed 120 s timeout applies to `fastboot flash`/`adb backup` `[JUDG][VERIFY]`**
Killing fastboot mid-write can half-write a partition; multi-GB images exceed
120 s. The timeout was listed as a mitigation but for flashing it is the hazard.
*Fix:* per-key timeouts (flash: none), progress message, and on timeout tell the
user not to power-cycle.

### MEDIUM

- **M1. `--runner` fails open; env var ignored `[DET]`.** Any value but
  `container` silently became `LocalRunner`; the option default overwrote
  `ANDROID_AGENT_RUNNER`. *Fixed* (Enum + env default).
- **M2. Documented config not applied `[DET]`.** `OLLAMA_HOST` /
  `ANDROID_AGENT_OLLAMA_MODEL` were read into `Config` but never passed to
  `OllamaLLM`. *Fixed.* Verify `claude-opus-4-8` is a valid model id before release.
- **M3. Container sandbox weaker than documented `[JUDG][VERIFY]`.** `--network
  none` is Linux-only; no `--cap-drop`/`no-new-privileges`/`--read-only`/limits;
  image runs as root; `:latest` and un-pinned base; host image dir not mounted,
  so flash in container mode likely can't find the file on Windows/macOS.
  *Fixed* — hardening flags (cap-drop ALL, no-new-privileges, read-only root +
  `/tmp` tmpfs, PID/memory limits) and a non-root user added; base-image digest
  pinning documented; ROM images named in a command are bind-mounted read-only
  and their paths rewritten, so `flash-rom` works in the container on Linux
  (USB-level flashing on Windows/macOS still uses the host runner).
- **M4. LLM plans validated for shape, not meaning `[DET][JUDG]`.** Mission
  override via payload; no per-step mission scope; `human` text unrelated to the
  command; protected-package/option checks not applied to LLM steps. *Partially
  fixed* (mission scope, protected package, merge order).
- **M5. Flash/backup guardrails documented but not enforced `[DET]`.** No backup
  step, no unlock check, no image hash, no partition denylist; `adb backup -f`
  could overwrite an arbitrary host file. *Partially fixed* (backup removed).
- **M6. Untrusted device data in prompt; hosted-LLM egress undisclosed `[JUDG]`.**
  `device_facts` dumped into the prompt without "data not instructions" framing;
  serial/app inventory leave the machine with `--llm anthropic` and the consent
  text doesn't mention it. *Fixed* — facts wrapped in a delimited, size-capped
  `<device_facts>` block labelled untrusted in both prompts, and an explicit
  egress notice is shown before planning on a hosted backend.
- **M7. Security docs claimed controls the code didn't provide `[DET]`.** *Fixed.*
- **M8. Security-path test gaps; no coverage tooling `[DET]`.** `Bridge`,
  `propose`, both LLM adapters, HIGH-risk confirm untested; no `pytest-cov`
  threshold. *Fixed* — `pytest-cov` with an 80% `fail_under` floor; both LLM
  adapters, the sandbox hardening/env-scrub, the hash-chained log and the
  `run`/`devices`/`log` CLI paths are now covered (106 tests).
- **M9. CI/supply-chain gaps `[DET]`.** Actions pinned by mutable tag; no
  Dependabot cooldown; CI ignores `uv.lock`; no SAST/SCA/secret/SBOM job.
  *Fixed* — actions SHA-pinned, a `uv sync --frozen` job validates the lockfile,
  a `pip-audit` SCA job runs, and Dependabot has a release cooldown. (ruff's `S`
  rules remain the SAST layer; a dedicated SBOM-diff job is a future nicety.)

### LOW
- **L1.** `.coverage` tracked in git. *Fixed* (removed + gitignored).
- **L2.** Default Typer `pretty_exceptions_show_locals` could print an API key;
  model/network errors unhandled. *Fixed* — locals already off; unreachable
  backend / malformed / truncated output now abort with a clear message.
- **L3.** Child processes inherit full env (incl. API key); Windows `shutil.which`
  searches CWD on Python <3.12. *Fixed* — toolchain env scrubbed of LLM keys;
  a CWD-resolved tool is rejected on Windows.
- **L4.** Action log best-effort, not tamper-evident; plans for debloat/flash-rom
  not logged; consent/confirm not recorded. *Fixed* — hash-chained entries +
  `verify()`; consent, confirm and debloat/flash-rom plans are now logged.
- **L5.** `typer.confirm` has no TTY check (`yes |` auto-answers); "Type yes"
  accepts `y`. *Fixed* — HIGH-risk gate requires the literal word `yes`, which
  a piped `yes |` (sending `y`) cannot satisfy.
- **L6.** Stale docs/counts (test count, "stub" docstrings, ADR 0005 wording).
  *Fixed.*
- **L7.** `parse_fastboot_devices` treats any non-empty line's first token as a
  serial; prompt/`max_tokens` truncation unchecked. *Fixed* — only lines whose
  second field is `fastboot` are devices; a `max_tokens`-truncated hosted plan
  is rejected rather than parsed.
- **L8.** `anthropic` extra unverified against the locked SDK; adapter 0%
  coverage; never installed in CI. *Fixed* — adapter now has unit tests and the
  extra is installed in the CI test matrix.

### INFO
- **I1.** Bandit B101 (108) is test-only noise; B404/B603 in `sandbox.py` are the
  expected argv use.
- **I2.** Positives to keep: single bridge chokepoint and `shell=False`; risk
  derived from the allowlist and only ratcheted up; unmapped keys default to
  HIGH; flash target check refuses when `product` is unreadable; ADRs, STRIDE,
  `py.typed`, `uv.lock`, Dependabot, private vuln reporting, Windows+Linux
  matrix; excellent complexity/duplication metrics.

## Deterministic results

| Tool | Result |
|---|---|
| ruff (incl. bandit `S`) | 0 issues; format OK |
| mypy | 0 errors, 29 files |
| Semgrep | 5 (Dependabot cooldown x2, mutable Action tag x2, Dockerfile no `USER`) |
| Bandit | 110 notes (108 B101 in tests; B404/B603 expected) |
| Trivy fs | 0 vulns, 0 secrets, Dockerfile DS002 HIGH (root) + DS026 LOW |
| SBOM | 46 components → `audits/sbom/android-agent-2026-11-04.cdx.json` |
| jscpd | 0.63% duplication |
| lizard | avg CCN 2.01, max 9 |
| pytest + cov | 62 passed, 72% coverage |

Coverage was weakest in `bridge/device.py` (47%), the LLM adapters (0%) and
`cli.py` (56%) at audit time; CLI and plan-validation tests were added in the
follow-up.

## Method and limits

Advisory only; no source file was modified by the audit (only the SBOM and this
report are written). Repo content was treated as untrusted data. No secrets were
found. Real-device, container-run and live-LLM behaviour were not executed
(`[VERIFY]`).
