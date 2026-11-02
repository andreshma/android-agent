# 0005. Sandbox runner port (local + container)

- Status: Accepted
- Date: 2026-11-02

## Context and problem statement

The `adb`/`fastboot` toolchain, and payloads coming off a device, are a risk to
the host and could reach the network. We want the option to contain the
toolchain without changing the layers above, and it must work on Windows and
Linux.

## Decision drivers

- Containment of a compromised toolchain or device payload.
- Cross-platform: tool resolution and USB access differ by OS.
- No change to capabilities/bridge when swapping execution mode.

## Considered options

- **A. A `Runner` port** with `LocalRunner` (direct) and `ContainerRunner`
  (network-less container, USB passthrough), selected by config.
- **B. Always run locally.**

## Decision

Option **A**. `sandbox.Runner` is a port; `LocalRunner` resolves tools via
`shutil.which` (honouring `PATHEXT` on Windows, PATH on Linux/macOS, with env
overrides) and runs `argv` with `shell=False`. `ContainerRunner` is specified
(Linux: `--device=/dev/bus/usb`; Windows/macOS: adb server over loopback) with a
defined interface; implementation is a tracked contributor task.

## Consequences

- Positive: containment is opt-in and transparent to upper layers.
- Positive: cross-platform tool resolution handled in one place.
- Negative: the container adapter is not implemented yet (interface frozen).
