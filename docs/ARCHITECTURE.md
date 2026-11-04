# Architecture

android-agent is a layered, ports-and-adapters design. Each layer depends only
on the one below it through a narrow interface, which keeps the security
boundary in one place and makes every external dependency (the LLM, the device
toolchain) swappable and testable.

## C4 — Context

```mermaid
flowchart TD
    op([Operator — owns the device])
    agent["android-agent (CLI)"]
    llm["LLM backend<br/>Ollama / Claude"]
    dev["Android device<br/>adb / fastboot"]
    cont[("container sandbox<br/>(optional)")]

    op -- "intent / confirmation" --> agent
    agent -- "plain-language plans & results" --> op
    agent --> llm
    agent --> dev
    agent -. "--runner container" .-> cont
    cont --> dev
```

## C4 — Container / layers

```mermaid
flowchart TD
    cli["CLI · cli.py<br/>consent · plan · --drill-down · confirm (extra for HIGH)"]
    orch["Orchestrator · orchestrator.py<br/>propose → annotate risk → run — no I/O, testable"]
    caps["Capabilities · capabilities/*.py<br/>audit · optimize · flash · unlock · inspect"]
    llm["LLM port · llm/*.py<br/>base.LLM ← ollama · anthropic_llm (factory)"]
    bridge["Device Bridge · bridge/device.py<br/>validate → inject serial → run"]
    allow[["Allowlist · bridge/allowlist.py<br/>security boundary"]]
    sandbox["Sandbox Runner · bridge/sandbox.py<br/>LocalRunner | ContainerRunner (argv, shell=False)"]
    hw["adb / fastboot → device"]

    cli --> orch
    orch --> caps
    orch --> llm
    caps --> bridge
    bridge --> allow
    allow --> sandbox
    sandbox --> hw
```

## The core contract: propose → confirm → execute

```mermaid
flowchart TD
    f["inspect.gather_facts + capability.gather_facts<br/>(read-only snapshot)"]
    p["llm.propose_plan(mission, request, facts)<br/>→ Plan (untrusted)"]
    a["orchestrator.annotate_plan_risk<br/>validate · mission-scope · re-derive risk"]
    s["CLI shows plan summary + steps<br/>(--drill-down → raw argv)"]
    c{"operator confirms<br/>HIGH ⇒ extra yes"}
    e["Orchestrator.run · per step:<br/>require_authorized → with_serial → allowlist.validate → execute<br/>(stop on a failed state-changing step)"]
    x([Aborted])

    f --> p --> a --> s --> c
    c -->|yes| e
    c -->|no| x
```

## Design patterns used

- **Ports & Adapters (Hexagonal).** `llm.base.LLM` and `sandbox.Runner` are
  ports; Ollama/Anthropic and Local/Container are adapters. The core
  (orchestrator, capabilities) depends on the ports only.
- **Strategy.** The LLM backend and the sandbox runner are interchangeable
  strategies chosen at runtime by a factory / config.
- **Command.** A `Step` is a validated, self-describing command object (with a
  human description, risk, and an `undo`); a `Plan` is a sequence of them.
- **Facade.** `Bridge` is the single facade over the device toolchain; nothing
  else calls `subprocess`.
- **Guard clause / policy at the boundary.** `allowlist.validate` and
  `consent.require_authorized` are enforced at the chokepoint, not sprinkled.

## Key invariants (do not break)

1. The LLM output is untrusted; it can only ever result in an **allowlisted**
   command, and each step's **risk is derived from the allowlist**
   (`allowlist.risk_for`), never trusted from the model.
2. Commands are `argv` lists, executed with `shell=False` — never shell strings.
3. No capability runs without `require_authorized(device)`.
4. Every executed command targets the authorized serial (`with_serial`).
5. The orchestrator performs no I/O and asks no questions — the CLI (or a future
   UI) owns all interaction, so the core stays unit-testable.

## Where decisions are recorded

Architecture Decision Records live in [`docs/adr/`](adr/). Start with
[the index](adr/README.md).
