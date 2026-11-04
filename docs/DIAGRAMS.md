# Diagrams

Rendered by GitHub automatically (Mermaid). They complement the prose in
[ARCHITECTURE.md](ARCHITECTURE.md).

## System context (C4 level 1)

```mermaid
flowchart TB
    operator([Operator<br/>owns the device])
    subgraph host[This machine]
        agent[android-agent CLI]
        llm_local[Ollama<br/>local LLM]
        tools[adb / fastboot]
        container[(optional<br/>container sandbox)]
    end
    llm_api[Claude API<br/>hosted LLM]
    device[Android device<br/>USB]

    operator -- intent / confirmation --> agent
    agent -- plain-language plan & results --> operator
    agent -- facts / plan request --> llm_local
    agent -. opt-in .-> llm_api
    agent -- allowlisted argv --> tools
    tools -- USB --> device
    agent -. --runner container .-> container
    container --> tools
```

## Layers / containers (C4 level 2)

```mermaid
flowchart TB
    cli[CLI · Typer + Rich<br/>consent · show plan · drill-down · confirm]
    orch[Orchestrator<br/>propose → annotate risk → run]
    caps[Capabilities<br/>audit · optimize · flash · unlock · inspect]
    llm[LLM port<br/>Ollama · Claude]
    bridge[Device Bridge<br/>single doorway]
    allow[[Allowlist<br/>security boundary]]
    sandbox[Sandbox Runner<br/>Local · Container]
    hw[adb / fastboot]

    cli --> orch
    orch --> caps
    orch --> llm
    caps --> bridge
    bridge --> allow
    allow --> sandbox
    sandbox --> hw
```

## The propose → confirm → execute flow

```mermaid
sequenceDiagram
    actor Op as Operator
    participant CLI
    participant Orch as Orchestrator
    participant LLM
    participant Cap as Capability
    participant AL as Allowlist
    participant Dev as Device

    Op->>CLI: run <mission> "request" -s SERIAL
    CLI->>CLI: consent gate (per-serial)
    CLI->>Orch: propose(device, mission, request)
    Orch->>Orch: require_mode(device, mission)
    Orch->>Cap: gather_facts (read-only)
    Cap->>Dev: allowlisted reads
    Orch->>LLM: propose_plan(facts)
    LLM-->>Orch: Plan (untrusted)
    Orch->>AL: validate + risk_for each step
    AL-->>Orch: authoritative risk / deny
    Orch-->>CLI: Plan (risk re-derived)
    CLI->>Op: show plan (+ drill-down)
    Op->>CLI: confirm (extra yes if HIGH)
    CLI->>Orch: run(device, plan)
    loop each step
        Orch->>Cap: execute_step
        Cap->>AL: validate(command)
        Cap->>Dev: inject serial → execute
        Orch->>Orch: log step
    end
    Orch-->>CLI: results
    CLI->>Op: per-step outcome
```

## Trust boundaries (data flow)

```mermaid
flowchart LR
    subgraph untrusted_in[Untrusted input]
        devdata[Device output<br/>app names, props]
        plan[LLM Plan]
    end
    boundary{{Allowlist + risk_for<br/>consent + serial inject}}
    subgraph trusted[Trusted execution]
        exec[argv · shell=false]
    end
    devdata --> plan
    plan --> boundary
    boundary -- permitted only --> exec
    boundary -- denied --> reject[Rejected]
```
