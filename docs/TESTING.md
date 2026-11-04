# Testing

## Automated tests

Pure logic (parsers, allowlist, consent, planning, logging) is covered by the
unit suite and runs with no device:

```bash
pytest -q
ruff check .
mypy src
```

CI runs this matrix on **Windows and Linux** across Python 3.10–3.12.

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
