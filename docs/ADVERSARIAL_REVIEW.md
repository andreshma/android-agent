# Adversarial Review

> **Honesty note (2026-11-04).** An independent 360° audit run after this pass
> found that two scenarios rated "holds" below were in fact exploitable at the
> time: the allowlist validated a command's *shape* but not its *arguments*
> (so `adb shell getprop ro.x $(reboot)` passed — scenario 1), and `with_serial`
> honored a supplied `-s OTHER` (scenario 4). Both are now fixed (per-key
> argument validators; the selector is always stripped and replaced). The
> lesson: a self-run red team is not a substitute for an independent audit. See
> [`../audits/`](../audits/) for the full report and remediation status.

A red-team pass over android-agent: instead of checking that the happy path
works, each scenario below assumes an attacker (a malicious device payload, a
compromised or manipulated LLM, a hostile input) and asks *what could go wrong,
and does the design hold?* Scenarios are rated by whether the design **holds**,
holds **with a caveat**, or required a **fix** (applied in this pass).

## Attacker model

- The connected device may be hostile or carry attacker-controlled data (app
  names, properties, dumpsys output).
- The LLM may be manipulated (prompt injection via device data) or its transport
  tampered with (a wrong/hostile plan comes back).
- CLI inputs (flags, image paths, partition names) may be crafted.
- Out of scope: an attacker with root on the host (they already win), and
  anything the operator is explicitly authorized to do to their own device.

## Scenarios

### 1. Prompt injection from device data → arbitrary command — **FIXED after audit**
A malicious app sets its label to `; rm -rf /` or `$(reboot)`, or instructs the
model to run a destructive command, and the model echoes it into a plan.
**Status:** `argv` + `shell=False` blocks host-side shell injection, but the
audit showed the allowlist originally checked only the sub-command prefix, so a
free-form argument like `$(reboot)` after `getprop` reached the *device* shell
(which re-parses `adb shell` args). Now fixed: each key has an argument
validator (regex per position, fail-closed) and the metacharacter set is
expanded, so injected arguments are denied.

### 2. LLM understates risk to skip the HIGH-risk gate — **HOLDS (fixed earlier)**
A manipulated plan labels `fastboot flashing unlock` as `risk: low` to avoid the
extra confirmation.
**Why it holds:** risk is re-derived from the command via `allowlist.risk_for`
in `orchestrator.annotate_plan_risk`; the model's self-declared risk is never
trusted over the allowlist, and the derived risk only ever ratchets *up*.

### 3. Smuggle a command into an off-mission plan — **HOLDS**
An `audit` plan secretly contains a `fastboot flash` step.
**Why it holds:** (a) the device-mode guard means an audit runs only in adb mode,
where fastboot commands can't execute; (b) every step is still allowlist-checked
and risk-derived at propose time, so a destructive step is surfaced as HIGH and
rejected if not permitted.

### 4. Redirect an action to another device — **FIXED after audit**
The plan targets a different serial (another phone on the same host) by setting
`-s OTHER` itself.
**Status:** the audit showed `with_serial` originally returned the command
unchanged when `-s` was already present, so `-s OTHER` was honored. Now fixed:
any supplied selector is stripped and replaced with the authorized serial, so an
action can only ever hit the consented device.

### 5. Flash an image for the wrong model → brick — **HOLDS**
The operator (or a bad instruction) points a Pixel image at a different device.
**Why it holds:** `FlashCapability.require_target` verifies `fastboot getvar
product` against the declared target and refuses on mismatch — and refuses when
the product can't be read at all (fail-safe).

### 6. Argument injection via partition / image name — **FIXED in this pass**
`argv` blocks *command* injection, but a value like `--version` or `-w` passed
as a partition or image path could be parsed by `fastboot` as an *option*
(`fastboot flash --version …`), changing the operation.
**Fix:** `flash._reject_option_like` rejects any partition or image path that
starts with `-` (and empties), closing option injection. Covered by a test.

### 7. Log tampering / injection — **HOLDS**
A command containing newlines or JSON could corrupt the action log.
**Why it holds:** the log serializes structured fields with `json.dumps`
(one object per line); commands are lists, not interpolated strings, so no
line-break can forge a second record.

### 8. Secret (API key) exposure — **HOLDS WITH CAVEAT**
The hosted-LLM API key could leak into the device, logs, or terminal.
**Why it holds:** the key is read from the environment, never written to the
device and never logged (the action log records commands, not LLM payloads).
**Caveat:** audit data sent to a hosted backend does leave the machine — hence
Ollama-local is the default, and the hosted backend is opt-in.

### 9. Toolchain / device payload reaching the host or network — **HOLDS WITH CAVEAT**
A compromised `adb`/`fastboot` binary or a malicious device payload tries to
touch the host filesystem or phone home.
**Why it holds:** the optional `ContainerRunner` runs the toolchain in a
network-less container (USB passthrough on Linux; host adb server over the
gateway on Windows/macOS).
**Caveat:** the operator must build and trust the container image; on
Windows/macOS USB isn't isolated from the host the way it is on Linux.

### 10. Resource exhaustion (huge dumpsys output) — **HOLDS WITH CAVEAT**
A hostile device returns an enormous `dumpsys`/`batterystats` dump.
**Why it holds:** every bridge call has a timeout, so a hang is bounded.
**Caveat:** output is captured fully in memory; a pathological dump could use a
lot of RAM. Streaming/bounded reads are a possible future hardening.

## Summary

| # | Scenario | Verdict |
|---|---|---|
| 1 | Prompt injection → command | **Fixed after audit** |
| 2 | Understated risk | Holds |
| 3 | Off-mission command | Holds (mission-scope enforced) |
| 4 | Wrong-device targeting | **Fixed after audit** |
| 5 | Wrong-model flash | Holds |
| 6 | Option injection (partition/image) | **Fixed this pass** |
| 7 | Log injection | Holds |
| 8 | API key exposure | Holds (local-first) |
| 9 | Toolchain/payload containment | Holds (image trust caveat) |
| 10 | Resource exhaustion | Holds (bounded by timeout) |

The security model (allowlist + consent gate + authoritative risk + serial
injection + target verification) is sound in design. This self-run pass found
and fixed option injection (scenario 6); the independent 360° audit then found
two more real gaps this pass had wrongly rated "holds" (scenarios 1 and 4),
which are now fixed with per-key argument validation and mandatory serial
replacement. Remaining caveats are in [THREAT_MODEL.md](THREAT_MODEL.md) and the
audit's open items in [`../audits/`](../audits/).
