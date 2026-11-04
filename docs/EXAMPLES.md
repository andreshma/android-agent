# android-agent — Examples Cookbook

Copy-paste examples covering **every feature**. For the structured manual (setup,
device preconditions, safety model) see [USAGE.md](USAGE.md); read
[DISCLAIMER.md](../DISCLAIMER.md) before running anything destructive.

Commands are shown with the installed `android-agent` entry point. You can always
use `python -m android_agent …` instead. Outputs marked **(real)** are verbatim
from an actual run; others are illustrative.

Contents:
[Install](#1-install) · [Pointing at adb/fastboot](#2-pointing-at-adbfastboot) ·
[Choosing a backend](#3-choosing-an-llm-backend) ·
[devices](#4-devices) · [run audit](#5-run-audit-read-only) ·
[run optimize](#6-run-optimize) · [debloat](#7-debloat-deterministic) ·
[flash-rom](#8-flash-rom-deterministic-high-risk) · [run unlock](#9-run-unlock-high-risk) ·
[run flash](#10-run-flash-llm) · [log](#11-log) · [Container sandbox](#12-container-sandbox) ·
[Practice on an emulator](#13-practice-safely-on-an-emulator) ·
[Troubleshooting](#14-troubleshooting-examples) · [Full ROM walkthrough](#15-full-rom-flash-walkthrough)

---

## 1. Install

```bash
# Local checkout, with the hosted backend and dev tools
pip install -e ".[dev,anthropic]"

# Reproducible, pinned environment (uv)
uv sync --all-extras

# Minimal: just the tool with the default local (Ollama) backend
pip install -e .
```

Verify:

```bash
android-agent --help
android-agent devices --help      # per-command help, works for every command
```

---

## 2. Pointing at adb/fastboot

If `adb`/`fastboot` are on your `PATH`, nothing to do. Otherwise point the agent
at them explicitly.

**bash / Linux / macOS:**
```bash
export ANDROID_AGENT_ADB="$HOME/Android/Sdk/platform-tools/adb"
export ANDROID_AGENT_FASTBOOT="$HOME/Android/Sdk/platform-tools/fastboot"
```

**Windows PowerShell:**
```powershell
$env:ANDROID_AGENT_ADB   = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
$env:ANDROID_AGENT_FASTBOOT = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\fastboot.exe"
```

Or just add `…\platform-tools` to your `PATH`.

---

## 3. Choosing an LLM backend

The LLM is only used by the `run` command; `debloat`, `flash-rom`, `devices` and
`log` are deterministic and need no model.

**Ollama (local, default)** — device data never leaves the machine:
```bash
# one-time: install Ollama, then pull a model
ollama pull llama3.1

# optional overrides
export ANDROID_AGENT_OLLAMA_MODEL=llama3.1
export OLLAMA_HOST=http://localhost:11434
```

**Claude API (hosted)** — more capable planning; read-only device facts are sent
to Anthropic:
```bash
pip install -e ".[anthropic]"
export ANTHROPIC_API_KEY=sk-ant-...
export ANDROID_AGENT_LLM=anthropic                 # make it the default
export ANDROID_AGENT_ANTHROPIC_MODEL=claude-opus-4-8   # optional
```
PowerShell:
```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
$env:ANDROID_AGENT_LLM = "anthropic"
```

**Override per run** without changing the default:
```bash
android-agent run audit "what's installed?" -s ABCD1234 --llm anthropic
android-agent run audit "what's installed?" -s ABCD1234 --llm ollama
```

When you select the hosted backend, the CLI shows an egress notice before it
plans:
```
╭─ Data leaves your machine ─────────────────────────────────────────────╮
│ You selected a HOSTED LLM backend (anthropic). Read-only device facts   │
│ (model, product, installed package names, system properties) will be    │
│ sent to that third-party API to plan this mission. Use the default      │
│ ollama backend to keep all device data on this machine.                 │
╰─────────────────────────────────────────────────────────────────────────╯
```

---

## 4. `devices`

```bash
android-agent devices
```

No device connected:
```
No devices detected. Connect a device with USB debugging on.
```

With a device/emulator connected — **(real)**:
```
• emulator-5554 (adb) sdk_gphone64_x86_64
```

A phone in the bootloader shows as `(fastboot)`. Use the container runner for
discovery too:
```bash
android-agent devices --runner container
```

---

## 5. `run audit` (read-only)

Ask, in plain language, what you want to know. Nothing changes on the device.

```bash
android-agent run audit "which apps can use my microphone and location?" -s ABCD1234
android-agent run audit "list everything installed and flag anything unusual" -s ABCD1234 --drill-down
```

`--drill-down` adds the raw command column:
```
┏━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ # ┃ What it does              ┃ Risk ┃ Reversible ┃ Command                  ┃
┡━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 1 │ Read the Android version  │ none │ —          │ adb -s ABCD1234 shell    │
│   │                           │      │            │ getprop ro.build.version │
└───┴───────────────────────────┴──────┴────────────┴──────────────────────────┘
```

You'll be asked for consent, then to run the plan (`y`).

---

## 6. `run optimize`

The LLM looks at installed apps and battery stats and proposes **reversible**
changes.

```bash
android-agent run optimize "my phone is slow and the battery drains fast" -s ABCD1234
android-agent run optimize "disable apps I never use" -s ABCD1234 --drill-down
```

Every step is `low` risk and reversible (the app stays installed). If a step
fails, the rest are skipped and you're warned.

---

## 7. `debloat` (deterministic)

No LLM. Detects likely-bloatware (OEM/carrier/preinstalls) and proposes disabling
them. Core/system apps are protected and never flagged.

```bash
android-agent debloat -s ABCD1234 --drill-down
```

**(real)** — a run against the emulator; detection + plan, then declined:
```
Plan · optimize
Disable 1 likely-bloatware app(s) found on the device. All changes are
reversible (the apps stay installed and can be re-enabled).

 # │ What it does                                   │ Risk │ Reversible │ Command
 1 │ Disable 'com.google.android.googlequicksearch… │ low  │ yes        │ adb -s emulator-5554 shell pm disable-user com.google.android.googlequicksearchbox
Run this plan now? [y/N]: n
Aborted.
```

**(real)** — confirming it, then verifying with adb and re-enabling:
```
$ android-agent debloat -s emulator-5554 --no-log      # input: y (consent), y (run)
1. ok — Disable 'com.google.android.googlequicksearchbox' — Google app / Assistant.

$ adb -s emulator-5554 shell pm list packages -d | grep googlequicksearchbox
package:com.google.android.googlequicksearchbox        # now disabled

$ adb -s emulator-5554 shell pm enable com.google.android.googlequicksearchbox
Package com.google.android.googlequicksearchbox new state: enabled   # reversed
```

Turn logging off, or send it elsewhere:
```bash
android-agent debloat -s ABCD1234 --no-log
ANDROID_AGENT_LOG=./run.jsonl android-agent debloat -s ABCD1234
```

---

## 8. `flash-rom` (deterministic, HIGH risk)

Verified, ordered ROM flash. Needs the device in **fastboot** mode. Refuses
unless `--product` matches the connected device, and checks every image exists.

```bash
# Single partition
android-agent flash-rom -s ABCD1234 --product redfin --image boot=./boot.img

# Multiple partitions (flashed in a safe recommended order automatically)
android-agent flash-rom -s ABCD1234 --product redfin \
  --image boot=./boot.img \
  --image system=./system.img \
  --image vendor=./vendor.img \
  --drill-down
```

**Windows paths work** (spaces and backslashes included):
```powershell
android-agent flash-rom -s ABCD1234 --product redfin `
  --image "boot=C:\Users\me\roms\boot.img" `
  --image "system=C:\Users\me\Program Files (x86)\roms\system.img"
```

HIGH-risk confirmation requires typing the literal word `yes` (a bare `y` is
rejected):
```
This plan contains HIGH-risk, irreversible steps (data may be erased).
Type the word 'yes' to confirm you understand and want to proceed: yes
Run this plan now? [y/N]: y
1. ok — Write the image './boot.img' to the 'boot' partition…
2. ok — Write the image './system.img' to the 'system' partition…
3. ok — Reboot the device to finish and boot the new ROM.
```

Wrong target is refused (fail-safe):
```
$ android-agent flash-rom -s ABCD1234 --product sunfish --image boot=./boot.img
Refusing to flash: Device ABCD1234 is not the expected flash target 'sunfish'.
Refusing to flash to avoid bricking it.
```

---

## 9. `run unlock` (HIGH risk)

Unlock **your own** bootloader (device in fastboot, OEM unlocking enabled). This
ERASES ALL DATA and the phone asks you to confirm on its screen.

```bash
android-agent run unlock "unlock my own bootloader" -s ABCD1234
```
```
This plan contains HIGH-risk, irreversible steps (data may be erased).
Type the word 'yes' to confirm you understand and want to proceed: yes
Run this plan now? [y/N]: y
1. ok — Unlock the bootloader of your own device…
```

> Out of scope: this never bypasses a lock screen, FRP, or a carrier lock, and
> it can't unlock a device whose owner didn't enable OEM unlocking.

---

## 10. `run flash` (LLM)

Like `flash-rom` but the LLM assembles the plan from your request (device in
fastboot). Use `flash-rom` when you want the deterministic, verified walkthrough.

```bash
android-agent run flash "flash the boot.img in my current folder" -s ABCD1234 --drill-down
```

---

## 11. `log`

Every run (unless `--no-log`) appends to a hash-chained JSONL log.

```bash
android-agent log                       # most recent 20 entries
android-agent log --limit 100           # more history
android-agent log -s ABCD1234           # only this device
```
```
                               Action log
┏━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ When (UTC)          ┃ Device       ┃ Event           ┃ Detail                ┃
┡━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 2026-11-04T19:28:01 │ emulator-5554│ consent_recorded│ operator confirmed …  │
│ 2026-11-04T19:28:01 │ emulator-5554│ plan_proposed   │ optimize · 1 steps …  │
│ 2026-11-04T19:28:02 │ emulator-5554│ plan_confirmed  │ confirmed optimize …  │
│ 2026-11-04T19:28:02 │ emulator-5554│ step_executed   │ ok adb -s … disable…  │
└─────────────────────┴──────────────┴─────────────────┴───────────────────────┘
```

Check the log hasn't been tampered with:
```bash
python -c "from android_agent.audit_log import ActionLog; print('intact:', ActionLog().verify())"
```

---

## 12. Container sandbox

Run the toolchain inside a network-less, least-privilege container.

```bash
# Build the image once
docker build -t android-agent/adb-tools:latest -f docker/adb-tools.Dockerfile .

# Use it per command…
android-agent debloat -s ABCD1234 --runner container
# …or make it the default
export ANDROID_AGENT_RUNNER=container
android-agent devices
```

On Linux, USB is passed through and ROM images are bind-mounted read-only, so
`flash-rom` works in the sandbox. On Windows/macOS use `--runner local` for
fastboot flashing.

---

## 13. Practice safely on an emulator

An emulator appears as a normal adb device, so you can exercise the read-only and
optimize/debloat flows with zero risk to a real phone. This is exactly how the
tool was validated.

```bash
# Create/choose an AVD in Android Studio, then:
emulator -avd Medium_Phone_API_35 &          # start it (background)
adb wait-for-device                          # wait until it's online

# Point the agent at the SDK's adb and run a real (reversible) flow
export ANDROID_AGENT_ADB="$HOME/…/platform-tools/adb"
android-agent devices                        # shows emulator-5554 (adb)
android-agent debloat -s emulator-5554 --drill-down

# Shut the emulator down when done
adb -s emulator-5554 emu kill
```

Flash/unlock use fastboot, which a standard emulator doesn't support — validate
those on a real device following [TESTING.md](TESTING.md).

---

## 14. Troubleshooting examples

```bash
# adb not found → install platform-tools or set the path
$ android-agent devices
No devices detected. Connect a device with USB debugging on.
#   (set ANDROID_AGENT_ADB if it's installed but not on PATH)

# wrong mode → reboot to the bootloader for flash/unlock
$ android-agent run flash "…" -s ABCD1234
The 'flash' mission needs the device in fastboot mode, but ABCD1234 is in adb
mode. Reboot to the bootloader (e.g. `adb reboot bootloader`).

# a plan tried something off-mission → rejected by design
$ android-agent run audit "…" -s ABCD1234
Rejected the proposed plan: step 'fastboot flash …' is not allowed for the
'audit' mission

# hosted backend selected but extra missing
$ android-agent run audit "…" -s ABCD1234 --llm anthropic
The anthropic extra is not installed. Run: pip install android-agent[anthropic]
```

---

## 15. Full ROM-flash walkthrough

End-to-end, on your own device, using the agent for every step:

```bash
# 0. Enable Developer options + USB debugging + "OEM unlocking" on the phone.
# 1. Confirm it's visible
android-agent devices

# 2. BACK UP YOUR DATA (unlocking erases the device).

# 3. Reboot to the bootloader and unlock
adb reboot bootloader
android-agent devices                         # now shows (fastboot)
android-agent run unlock "unlock my own bootloader" -s ABCD1234
#   → type 'yes', confirm, then accept the prompt ON THE PHONE (it wipes & reboots)

# 4. Back to the bootloader for flashing
adb reboot bootloader

# 5. Flash the ROM images (verified, ordered)
android-agent flash-rom -s ABCD1234 --product redfin \
  --image boot=./boot.img --image system=./system.img --drill-down
#   → review, type 'yes', confirm; a failed step stops the sequence

# 6. The final step reboots into the new ROM.

# 7. Review what happened
android-agent log -s ABCD1234
```

> If a flash step fails: **do not power-cycle the device.** Read the error,
> re-enter fastboot, and re-flash the affected partition — a half-written
> partition is the classic brick scenario, which is why the agent stops on
> failure and never times out a flash mid-write.
