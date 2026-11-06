"""Runtime configuration.

Resolved from CLI flags and environment, with sensible defaults. The default
LLM backend is the local one (Ollama) to keep device data on the machine.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Single source of truth for the default hosted model id, so the CLI, the
# config and the Anthropic adapter can never drift apart (audit L12). Verify
# this id against the provider's models endpoint at release time.
DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-8"


@dataclass
class Config:
    llm_backend: str = "ollama"  # "ollama" | "anthropic"
    ollama_model: str = "llama3.1"
    ollama_host: str = "http://localhost:11434"
    anthropic_model: str = DEFAULT_ANTHROPIC_MODEL
    runner: str = "local"  # "local" | "container"

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            llm_backend=os.environ.get("ANDROID_AGENT_LLM", "ollama"),
            ollama_model=os.environ.get("ANDROID_AGENT_OLLAMA_MODEL", "llama3.1"),
            ollama_host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
            anthropic_model=os.environ.get(
                "ANDROID_AGENT_ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL
            ),
            runner=os.environ.get("ANDROID_AGENT_RUNNER", "local"),
        )
