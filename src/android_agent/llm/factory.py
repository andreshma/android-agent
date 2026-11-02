"""Pick an LLM backend by name, so the CLI and config stay backend-agnostic."""

from __future__ import annotations

from .base import LLM


def make_llm(backend: str, **kwargs) -> LLM:
    """Return an LLM implementation for ``backend`` ("ollama" | "anthropic")."""
    backend = backend.lower()
    if backend == "ollama":
        from .ollama import OllamaLLM

        return OllamaLLM(**kwargs)
    if backend in {"anthropic", "claude"}:
        from .anthropic_llm import AnthropicLLM

        return AnthropicLLM(**kwargs)
    raise ValueError(f"unknown LLM backend {backend!r} (choose: ollama, anthropic)")
