# Threat Model

A STRIDE-oriented look at android-agent. The system takes an operator's
natural-language intent, asks an LLM (local or hosted) to propose a plan, and
executes allowlisted `adb`/`fastboot` commands against the operator's own
device.

## Assets

| Asset | Why it matters |
|---|---|
| The connected device & its data | Flashing/unlock can erase it or brick it. |
| The host machine | The toolchain runs here; a bad command must not harm it. |
| Device data read during audit | May include package lists, properties — kept local by default. |
| The operator's API key (hosted LLM) | Secret; must not leak to logs or the device. |

## Trust boundaries

```
 operator ──intent──▶ CLI ──▶ Orchestrator ──facts──▶ LLM (local | hosted)
                                   │                      │
                                   │◀──────── Plan ───────┘   ← UNTRUSTED output
                                   ▼
                              Allowlist  ← trust boundary: nothing past here
                                   ▼        runs unless explicitly permitted
                              Bridge ▶ Sandbox runner ▶ adb/fastboot ▶ device
                                                                         ▲
                                       device output (pm list, props) ───┘
                                                           ← UNTRUSTED input
```

The **LLM output** and the **device output** are both treated as untrusted.

## STRIDE

### Spoofing
- *Wrong device targeted.* Mitigation: the authorized serial is injected into
  every command (`with_serial`); the LLM cannot redirect an action to another
  serial, and the consent gate is per-serial.

### Tampering
- *LLM proposes a destructive/arbitrary command.* Mitigation: the allowlist
  validates every `argv`; non-allowlisted sub-commands and shell metacharacters
  are rejected regardless of what the model asked for.
- *Malicious data on the device influences the plan* (prompt injection via an
  app name, property, etc.). Mitigation: device output is data, never executed;
  any command it tries to induce still has to pass the allowlist.

### Repudiation
- *No record of what ran.* Partial today (CLI prints results). Planned: an
  append-only action log of proposed vs. executed steps. See open items.

### Information Disclosure
- *Device data leaving the machine.* Mitigation: Ollama local backend is the
  default, so audit data stays on the host. The hosted backend is opt-in.
- *API key leakage.* Mitigation: key read from env, never written to the device
  or echoed; do not log request bodies.

### Denial of Service
- *Bricking the device.* Mitigation: flash is HIGH-risk, gated by an extra
  confirmation, a required backup step, and strict model/variant verification
  (`FlashCapability.require_target`) that refuses to flash unless the device's
  `product` matches the image's declared target — and refuses outright when the
  product can't be read (fail-safe).
- *Hung toolchain.* Mitigation: every bridge call has a timeout.

### Elevation of Privilege
- *Toolchain or device payload reaching the host/network.* Mitigation: the
  `ContainerRunner` runs adb/fastboot in a network-less container (USB passed
  through on Linux; host adb server over the gateway on Windows/macOS), so a
  compromised binary or payload is contained away from the host and internet.

## Residual risks / open items

- The container image must be built and trusted by the operator; a tampered
  image would undermine the sandbox (build it yourself from the provided
  Dockerfile).
- On Windows/macOS the container reaches the host adb server, a deliberately
  narrow channel; USB is not isolated from the host there as it is on Linux.
- The operator can still physically confirm a destructive action; the tool makes
  it *explainable and deliberate*, it does not remove the operator's authority
  over their own device.
