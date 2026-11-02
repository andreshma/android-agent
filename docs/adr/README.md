# Architecture Decision Records

We record significant, hard-to-reverse decisions as ADRs in the
[MADR](https://adr.github.io/madr/) format. Each file is immutable once
`Accepted`; a later decision supersedes an earlier one rather than editing it.

| # | Title | Status |
|---|---|---|
| [0001](0001-command-allowlist-boundary.md) | Command allowlist as the security boundary | Accepted |
| [0002](0002-ownership-consent-gate.md) | Ownership / consent gate, own-device scope | Accepted |
| [0003](0003-two-phase-plan-confirm-execute.md) | Two-phase propose → confirm → execute | Accepted |
| [0004](0004-pluggable-llm-backends.md) | Pluggable LLM backends (local + hosted) | Accepted |
| [0005](0005-sandbox-runner-port.md) | Sandbox runner port (local + container) | Accepted |

To add one, copy [`template.md`](template.md), take the next number, and add a
row above.
