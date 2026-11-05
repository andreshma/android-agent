# Testing

## Automated tests

Pure logic (parsers, allowlist, consent, planning, logging) is covered by the
unit suite, and **every user flow is emulated end-to-end** through the real CLI
with a fake bridge/LLM (`tests/test_flows_e2e.py`) — audit, optimize, debloat,
flash-rom, unlock, plus the guard rails (consent decline, wrong mode,
off-mission rejection, stop-on-failure, HIGH-risk typed-yes), hosted-backend
egress and the verifiable action log. It all runs with no device:

```bash
pytest -q          # unit + end-to-end flow emulation, with an 80% coverage floor
ruff check .
mypy src
```

CI runs this matrix on **Windows and Linux** across Python 3.10–3.12, plus a
locked-install (`uv --frozen`) job and a `pip-audit` supply-chain job.

## Validation status (what has actually been exercised)

Being precise about what has and hasn't been run against a real device, so the
coverage claims stay honest:

| Area | How it was validated | Status |
|---|---|---|
| `devices` discovery | Live against the Android emulator (API 35) | ✅ real device I/O |
| `audit` (read-only) | Live `run audit` against the emulator with **both** backends; 4 read-only adb steps executed | ✅ end-to-end, real adb |
| `debloat` disable → re-enable | Live on the emulator; reversibility confirmed independently via `adb shell pm enable` | ✅ reversible cycle |
| LLM round-trip | Live with **Ollama** (`llama3.1`) and **Claude** — plan proposed, parsed, risk re-derived | ✅ both backends |
| Allowlist guardrail | Live: a model-proposed non-allowlisted command (`pm list permissions` before it was added; a prefix-less command) was **rejected** before running | ✅ guardrail fired |
| `optimize` battery ranking | `battery.top_power_consumers` unit-tested on captured `dumpsys` output, **not** yet run live | ⚠️ parser tested, not live |
| `flash-rom` / `run flash` | Full suite + manual checklist; **cannot** run on an emulator (no fastboot flashing) | ⚠️ hardware-only, unverified live |
| `run unlock` (bootloader) | Suite + checklist; **cannot** run on an emulator | ⚠️ hardware-only, unverified live |
| Container runner (`--runner container`) | Unit-tested command construction; image must be built/trusted by the operator | ⚠️ construction tested |

The emulator cannot enter fastboot mode, so **flash and unlock have never been
exercised against real hardware by the maintainer** — they rest on the test
suite and the manual checklist below. Treat them accordingly and test on a
spare/own device you are prepared to wipe.

## Manual testing against a real device

The unit tests use fake bridges, so the one thing they can't cover is talking to
a physical phone. Use this checklist on **your own device** once you have
`adb`/`fastboot` installed.

### Prerequisites
- Android platform-tools on `PATH` (`adb version`, `fastboot --version`).
- USB debugging enabled on the device (Settings → Developer options).
- A USB cable; accept the "Allow USB debugging?" prompt on the phone.

### Read-only first (safe)
1. `android-agent devices` — the device shows up with serial + model.
2. `android-agent run audit "which apps can use my microphone?" -s <SERIAL> --drill-down`
   - Consent gate appears; confirm.
   - The plan/report lists apps with sensitive permissions.
3. `android-agent log -s <SERIAL>` — the audit appears in the trail.

### Reversible changes (low risk)
4. `android-agent debloat -s <SERIAL> --drill-down`
   - Review the detected bloatware list carefully before confirming.
   - Verify a disabled app disappears from the launcher.
   - Re-enable to confirm reversibility:
     `adb -s <SERIAL> shell pm enable <package>`.

### Destructive (HIGH risk — only on a device you are prepared to wipe)
5. Bootloader unlock / ROM flash require fastboot mode and **erase data**. Do
   these only on a spare/own device with a backup:
   - `adb -s <SERIAL> reboot bootloader`
   - `android-agent flash-rom -s <SERIAL> --product <codename> --image boot=boot.img ...`
   - Confirm it **refuses** if you pass the wrong `--product` (target check).

### What to report
If something misbehaves, open a bug with the output of the failing command, your
OS, and `adb`/`fastboot` versions. See `.github/ISSUE_TEMPLATE`.
