# 0004. Pluggable LLM backends (local + hosted)

- Status: Accepted
- Date: 2026-11-02

## Context and problem statement

Auditing a phone surfaces potentially private data, so some users need the model
to run locally; others want the strongest reasoning for planning a flash. We
need both without the core caring which is in use.

## Decision drivers

- Privacy: keep device data on the machine by default.
- Capability: allow a hosted model for harder planning.
- Testability: the core must not depend on a concrete provider.

## Considered options

- **A. An `LLM` port with Ollama and Anthropic adapters**, chosen by a factory,
  both producing the same structured `Plan`.
- **B. Hardcode a single provider.**

## Decision

Option **A**. `llm.base.LLM` defines `propose_plan` and `explain`; `OllamaLLM`
(local, **default**) and `AnthropicLLM` (hosted, opt-in extra) implement it;
`llm.factory.make_llm` selects by name/config. A shared `llm/schema.py` holds
the one JSON contract both backends fill (Ollama via JSON mode, Claude via tool
use).

## Consequences

- Positive: privacy-by-default; swappable; one output contract to maintain.
- Positive: new backends are a single adapter + factory line.
- Negative: structured output quality varies by local model (documented).
