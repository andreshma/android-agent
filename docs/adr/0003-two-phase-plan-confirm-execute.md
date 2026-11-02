# 0003. Two-phase propose → confirm → execute

- Status: Accepted
- Date: 2026-11-02

## Context and problem statement

Users need to understand and approve what the agent will do before it touches
their device, in plain language, with the option to inspect the exact command.
The agent must never act in one shot off a model response.

## Decision drivers

- Explainability for non-expert operators.
- A clear approval point, with stronger friction for destructive steps.
- Keep the core testable and reusable by a future GUI.

## Considered options

- **A. Structured `Plan` of `Step`s**, shown in plain language with optional
  drill-down, confirmed before execution; HIGH-risk needs an extra yes.
- **B. Free-text answer** from the LLM that the CLI runs directly.

## Decision

Option **A**. The LLM returns a `Plan` (summary + steps, each with a human
description, risk level, reversibility and `undo`). The CLI shows it,
`--drill-down` reveals raw `argv`, the operator confirms, and HIGH-risk plans
require a second explicit confirmation. The `Orchestrator` does no I/O and asks
nothing — interaction lives in the CLI.

## Consequences

- Positive: no surprise actions; human-readable by default, precise on demand.
- Positive: orchestrator/core is unit-testable; a GUI can reuse it unchanged.
- Negative: backends must produce structured output (handled via JSON mode /
  tool use).
