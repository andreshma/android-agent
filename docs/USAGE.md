# android-agent — User Manual

A step-by-step guide to everything android-agent can do with your own Android
device, the dependencies and preconditions it needs, and the full workflows
(including flashing). For **copy-paste examples of every feature**, see the
[Examples Cookbook](EXAMPLES.md). For the design and security rationale see
[ARCHITECTURE.md](ARCHITECTURE.md) and [THREAT_MODEL.md](THREAT_MODEL.md).

> ⚠️ **Read [DISCLAIMER.md](../DISCLAIMER.md) first.** Flashing and unlocking can
> erase all data, brick the device, and void its warranty. You run every action
> on your own responsibility, on a device you own or are authorized to modify.
> This tool never bypasses lock screens, FRP, or carrier locks.

---

## 1. What it does

android-agent sits between what you *want* in plain language and the exact
`adb`/`fastboot` commands that do it. Every mission follows the same contract:

```
gather read-only facts → LLM proposes a plan → you see it in plain language
→ you confirm (an extra typed "yes" for HIGH-risk) → it runs, step by step
```

Four missions and three helper commands:

| Capability | Command | Risk | Reversible |
|---|---|---|---|
| Audit what's installed & which apps hold sensitive permissions | `run audit` | none (read-only) | — |
| Optimize: disable bloatware, review battery drain | `run optimize` / `debloat` | low | yes |
| Flash a ROM / firmware image | `run flash` / `flash-rom` | **high** | no |
| Unlock the bootloader | `run unlock` | **high** | no |
| List connected devices | `devices` | none | — |
| Review the action log | `log` | none | — |

### 1.1 What it does **not** do (non-goals & limitations)

Being explicit about the edges keeps expectations honest. By deliberate design,
android-agent does **not**:

- **Create your backup.** `adb backup` was removed (its `-f <path>` was a
  host-file-overwrite vector, and modern Android backs it only partially). The
  backup before a destructive flash/unlock is a precondition **you** own (§3.3).
- **Install or uninstall apps.** There is no `adb install`, and
  `pm uninstall` / `cmd package uninstall` / `install-existing` are denied.
  `optimize`/`debloat` only **disable** packages (reversible) — nothing is
  removed from the device.
- **Sideload OTA zips or flash via recovery.** `adb sideload` is not supported;
  flashing is **fastboot partition images only** (`flash <partition> <image>`).
  A ROM distributed as a recovery-sideloaded zip is out of scope for now.
- **Factory-wipe or erase on request.** `fastboot -w` / `fastboot erase` are not
  allowlisted. (Unlocking the bootloader erases the device, but that wipe is
  performed by the device itself as part of `flashing unlock`, not a wipe
  command the agent issues.)
- **Re-lock as a guided mission.** The allowlist permits `fastboot flashing
  lock`, but there is no `relock` walkthrough — run it manually if you need it.
- **Expose diagnostics** such as `logcat`, `bugreport`, screenshots or
  screen-recording.
- **Bypass any security control.** No lock-screen, PIN, pattern, FRP (Factory
  Reset Protection) or carrier-lock bypass; nothing that targets a device you do
  not own. This is refused in code, not just in docs.
- **Run arbitrary commands.** Only the explicit allowlist
  (`bridge/allowlist.py`) runs; anything else the LLM proposes is rejected
  before you are asked to confirm.

If you need one of these, use `adb`/`fastboot` directly — on purpose, with full
knowledge of what you are doing.

---

## 2. Dependencies

### 2.1 Required

| Dependency | Why | How to get it |
|---|---|---|
| **Python ≥ 3.10** | Runs the agent | [python.org](https://www.python.org/) or your package manager |
| **Android platform-tools** (`adb` + `fastboot`) | Talk to the device | [developer.android.com/tools/releases/platform-tools](https://developer.android.com/tools/releases/platform-tools), or `apt install android-sdk-platform-tools` / `brew install android-platform-tools` / `choco install adb` |
| The `android-agent` package itself | The CLI | `pip install -e .` (from a clone) |

The Python runtime dependencies (`typer`, `rich`, `pydantic`, `httpx`,
`platformdirs`) are installed automatically with the package.

### 2.2 Choose at least one LLM backend

| Backend | When | Install |
|---|---|---|
| **Ollama** (local, default) | Keep all device data on your machine | Install [Ollama](https://ollama.com/), then `ollama pull llama3.1` (or your model) and make sure the server is running |
| **Claude API** (hosted) | More capable planning; you accept that read-only device facts are sent to Anthropic | `pip install -e ".[anthropic]"` and set `ANTHROPIC_API_KEY` |

**Choosing a model.** The agent asks the backend for a strict JSON plan whose
every command starts with `adb`/`fastboot` and sits on the allowlist. Capable
models — Claude, or a larger local model — follow that contract reliably. Small
or heavily-quantized local models sometimes drift (dropping the `adb` prefix, or
proposing a command that isn't allowlisted). When that happens the plan is
**rejected before anything runs** — a safe failure, not a dangerous one: just
re-run, or switch to a more capable model. In live testing `llama3.1` and Claude
both produced valid audit plans; very small models are more likely to be
rejected.

### 2.3 Optional — the container sandbox

| Dependency | Why |
|---|---|
| **Podman** or **Docker** | Run `adb`/`fastboot` inside a network-less, least-privilege container (`--runner container`) |

### 2.4 One-line installs

```bash
# From a clone of the repo:
pip install -e ".[dev,anthropic]"      # everything, for development
# or, pinned & reproducible with uv:
uv sync --all-extras
```

Verify the toolchain is visible:

```bash
adb version
fastboot --version
android-agent --help
```

If `adb`/`fastboot` aren't on your `PATH`, point the agent at them with
`ANDROID_AGENT_ADB` / `ANDROID_AGENT_FASTBOOT` (see §8).

---

## 3. Device preconditions

### 3.1 For audit / optimize (adb mode)

1. On the phone: **Settings → About phone → tap "Build number" 7 times** to
   enable Developer options.
2. **Settings → System → Developer options → enable "USB debugging".**
3. Connect the device by USB and **accept the "Allow USB debugging?" prompt** on
   the phone (tick "always allow from this computer").
4. Confirm it's visible:
   ```bash
   android-agent devices
   ```
   You should see your serial in `adb` mode.

### 3.2 For flash / unlock (fastboot mode)

1. Do everything in §3.1 first.
2. In **Developer options, enable "OEM unlocking"** (if it's greyed out, the
   device/carrier does not permit bootloader unlocking — that is out of scope,
   the tool cannot and will not force it).
3. Reboot into the bootloader:
   ```bash
   adb reboot bootloader
   ```
4. Confirm it's visible in fastboot:
   ```bash
   android-agent devices      # shows the serial in 'fastboot' mode
   ```

### 3.3 Always, before anything destructive

- **Back up your data.** Flashing and unlocking erase the device. The agent does
  not make the backup for you; it is a precondition you own.
- Know your **exact model/product codename** (e.g. `redfin` for a Pixel 5). The
  flash workflow refuses to run unless the connected device matches.

---

## 4. The two-phase flow (how a run feels)

```bash
android-agent run audit "what's installed and what has access to my mic?" -s ABCD1234
```

1. **Consent gate** — you confirm this is your device.
2. **Egress notice** — if you chose the hosted backend, it tells you device
   facts will leave the machine, before planning.
3. **Plan** — a plain-language summary and a numbered list of steps, each with
   its risk and whether it's reversible. Add `--drill-down` to also see the raw
   `adb`/`fastboot` command for every step.
4. **Confirm** — a normal `y/N`. If any step is HIGH-risk you must additionally
   **type the word `yes`** (a bare `y` is rejected, so a piped `yes |` can't
   auto-approve a destructive run).
5. **Execution** — steps run one at a time and each result is printed. If a
   state-changing step fails, the rest are **skipped** and you're warned the
   device may be in a partial state.

Everything is recorded to a tamper-evident log (see §7); add `--no-log` to
disable.

---

## 5. Command reference

### 5.1 `devices`
```bash
android-agent devices
android-agent devices --runner container
```
Lists every connected device in both `adb` and `fastboot` modes.

### 5.2 `run <mission> <request> -s <serial>`
The LLM-driven entry point. `mission` is `audit | optimize | flash | unlock`.

```bash
# Read-only audit
android-agent run audit "review privacy-sensitive permissions" -s ABCD1234

# Optimize (LLM proposes which apps to disable)
android-agent run optimize "my phone is slow and the battery drains fast" -s ABCD1234

# Flash via the LLM (fastboot mode)
android-agent run flash "flash the boot image I downloaded" -s ABCD1234

# Unlock the bootloader (fastboot mode, HIGH risk)
android-agent run unlock "unlock my own bootloader" -s ABCD1234
```

Common flags (all missions):

| Flag | Purpose |
|---|---|
| `-s, --serial` | **Required.** Target device serial. |
| `--llm ollama\|anthropic` | Override the backend for this run. |
| `--drill-down` | Show the raw command for each step. |
| `--runner local\|container` | Where the toolchain runs. |
| `--log / --no-log` | Record (or not) to the action log. |

### 5.3 `debloat -s <serial>`
A **deterministic** (no-LLM) optimize: detects likely-bloatware (OEM/carrier
preinstalls) and proposes a reversible plan that **disables** them (they stay
installed and can be re-enabled). Core/system apps are protected and never
flagged.

```bash
android-agent debloat -s ABCD1234 --drill-down
```

### 5.4 `flash-rom -s <serial> --product <codename> --image <part>=<path> …`
A **deterministic**, verified, ordered ROM-flash walkthrough (HIGH risk). It:

1. reads `fastboot getvar product` and **refuses unless it matches `--product`**
   (and refuses outright if the product can't be read),
2. checks every image file exists,
3. flashes partitions in a safe recommended order, then reboots.

```bash
android-agent flash-rom -s ABCD1234 --product redfin \
  --image boot=./boot.img \
  --image system=./system.img \
  --image vendor=./vendor.img
```

`--image` is repeatable; `partition=path`. See §6 for the full flashing
workflow.

### 5.5 `log [-s <serial>] [--limit N]`
Shows the recorded trail: consent, proposed plans, confirmations and executed
steps.

```bash
android-agent log --limit 50
android-agent log -s ABCD1234
```

---

## 6. The flashing workflow (in full)

Flashing is the highest-risk thing the tool does. Here is the complete, safe
sequence for installing a custom ROM on your own device.

> ⚠️ A wrong image for your exact model can **brick** the device. Only use
> images built for your precise product codename. The tool verifies this but
> cannot know whether *you* downloaded the right file.

1. **Enable OEM unlocking** and confirm the device appears in fastboot (§3.2).
2. **Back up everything** — unlocking the bootloader erases the device (§3.3).
3. **Unlock the bootloader:**
   ```bash
   android-agent run unlock "unlock my own bootloader" -s ABCD1234
   ```
   Confirm the plan, type `yes`, and then **accept the prompt on the phone's
   screen**. The device wipes and reboots.
4. Reboot back to the bootloader (`adb reboot bootloader`) and verify it's in
   fastboot again.
5. **Flash the ROM images** with the verified walkthrough:
   ```bash
   android-agent flash-rom -s ABCD1234 --product redfin \
     --image boot=./boot.img --image system=./system.img
   ```
   Review the ordered plan, type `yes`, confirm. Steps run one at a time; a
   failed step stops the sequence.
6. The final step reboots into the new ROM.

**If a flash step fails:** do **not** power-cycle the device. Read the printed
error, re-enter fastboot if needed, and re-flash the affected partition. A
half-written partition is the classic brick scenario, which is exactly why the
agent stops on failure and never times out a flash mid-write.

### Flashing inside the sandbox

On **Linux**, `--runner container` runs fastboot in a network-less container
with USB passed through; the ROM image files you reference are bind-mounted
read-only automatically. On **Windows/macOS**, USB can't be passed to the
container, so run `flash-rom` on the default `--runner local` there.

---

## 7. The action log

Every run appends to a JSONL log (default: your per-user log dir; override with
`ANDROID_AGENT_LOG`). Each entry is **hash-chained** to the previous one, so
editing, reordering or deleting an entry is detectable:

```python
from android_agent.audit_log import ActionLog
ActionLog().verify()   # True if the chain is intact
```

Recorded events: `consent_recorded`, `plan_proposed`, `plan_confirmed`,
`step_executed`. Your LLM API key is never written to the log, nor passed to the
`adb`/`fastboot` child process.

---

## 8. Configuration

All optional; sensible defaults are used.

| Variable | Default | Purpose |
|---|---|---|
| `ANDROID_AGENT_LLM` | `ollama` | Backend: `ollama` or `anthropic`. |
| `ANDROID_AGENT_OLLAMA_MODEL` | `llama3.1` | Ollama model name. |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL. |
| `ANDROID_AGENT_ANTHROPIC_MODEL` | `claude-opus-4-8` | Hosted model id. |
| `ANTHROPIC_API_KEY` | — | Required for the hosted backend. |
| `ANDROID_AGENT_RUNNER` | `local` | `local` or `container`. |
| `ANDROID_AGENT_ADB` | (PATH) | Explicit path to `adb`. |
| `ANDROID_AGENT_FASTBOOT` | (PATH) | Explicit path to `fastboot`. |
| `ANDROID_AGENT_LOG` | per-user log dir | Action-log file path. |

---

## 9. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `No devices detected` | USB debugging off, cable is charge-only, or you didn't accept the on-phone prompt. Re-check §3.1. |
| `'adb' not found` | platform-tools not on `PATH`; install it or set `ANDROID_AGENT_ADB`. |
| `The '…' mission needs the device in fastboot mode` | Reboot to the bootloader: `adb reboot bootloader`. |
| `Refusing to flash: Device … is not the expected flash target` | The connected product doesn't match `--product`, or it couldn't be read. Double-check the codename and that you're in fastboot. |
| `Could not reach the LLM backend` | Ollama server isn't running, or the network/host is unreachable. Start Ollama or switch backend. |
| `The anthropic extra is not installed` | `pip install -e ".[anthropic]"` and set `ANTHROPIC_API_KEY`. |
| A plan is `Rejected` | A proposed step was outside the mission's allowed commands or targeted a protected package — working as intended. |

---

## 10. Safety model in one paragraph

The LLM never runs shell. It returns a structured plan; every step is validated
against an `argv`-only allowlist (`shell=False`, per-argument regexes, shell
metacharacters rejected), its risk is re-derived from the command (the model's
self-reported risk is never trusted), and it's checked against the mission's
allowed command set and a protected-package list before you ever confirm. The
authorized serial is injected into every command so an action can't be
redirected to another device, and consent is required per serial. Full analysis:
[THREAT_MODEL.md](THREAT_MODEL.md).
