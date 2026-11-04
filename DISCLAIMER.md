# Disclaimer & Liability Waiver

**Read this before using android-agent.** By downloading, installing, or running
this software you acknowledge and accept everything below. If you do not accept
it, do not use the software.

## No warranty

android-agent is provided **"AS IS", without warranty of any kind**, express or
implied, including but not limited to the warranties of merchantability, fitness
for a particular purpose, and non-infringement. This restates the warranty
disclaimer of the project's [Apache License 2.0](LICENSE); the license controls
in case of any conflict.

## Use at your own risk

This tool runs `adb` and `fastboot` operations against a physical Android
device. Some of those operations are **inherently dangerous**. Flashing
firmware, unlocking the bootloader, disabling system packages, and similar
actions can, among other things:

- **permanently erase all data** on the device,
- **brick the device** (render it unbootable and possibly unrecoverable),
- **void the manufacturer's or carrier's warranty**,
- disable security features or trip verified-boot / integrity attestation,
- cause the device to malfunction in ways not listed here.

**You alone decide whether to run any proposed action, and you alone bear the
consequences.** The agent always shows a plan and waits for your explicit
confirmation; confirming is your decision. No amount of explanation,
verification, or safeguards in this tool removes the risk — they only make it
more visible and deliberate.

## Your responsibilities

By using android-agent you represent and agree that:

1. **You own the device**, or you have explicit, lawful authorization from its
   owner to perform the operations you run on it.
2. You will **not** use the tool to bypass a lock screen, Factory Reset
   Protection (FRP), a Google/Samsung/manufacturer account lock, a carrier lock,
   or any other security measure on a device you do not own or are not
   authorized to modify. The tool is not designed to do this and attempting it
   is outside its intended scope.
3. You are solely responsible for **complying with all laws, regulations, and
   contracts** that apply to you and the device in your jurisdiction, including
   warranty terms, carrier agreements, import/export rules, and any local law
   governing device modification.
4. You have **made your own backups** before running any destructive action.
   This tool does not guarantee any backup.
5. You understand the tool relies on an LLM (local or hosted) to propose plans,
   that LLM output can be wrong, and that the final decision to execute is
   always yours.

## Limitation of liability

To the maximum extent permitted by applicable law, **in no event shall the
authors, contributors, or copyright holders of android-agent be liable** for any
claim, damages, or other liability — whether in an action of contract, tort, or
otherwise — arising from, out of, or in connection with the software or its use,
including without limitation any **data loss, device damage ("bricking"),
voided warranty, financial loss, or legal consequence**, even if advised of the
possibility of such damage.

## Not legal advice

This document is a plain-language statement of the project's position, not legal
advice. If you are unsure whether a given operation is lawful or advisable in
your situation, consult a qualified professional before proceeding.
