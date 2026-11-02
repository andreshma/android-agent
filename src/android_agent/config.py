"""Runtime configuration.

Resolved from CLI flags and environment, with sensible defaults. The default
LLM backend is the local one (Ollama) to keep device data on the machine.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Config:
    llm_backend: str = "ollama"            # "ollama" | "anthropic"
    ollama_model: str = "llama3.1"
    ollama_host: str = "http://localhost:11434"
    anthropic_model: str = "claude-opus-4-8"
    runner: str = "local"                  # "local" | "container"

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            llm_backend=os.environ.get("ANDROID_AGENT_LLM", "ollama"),
            ollama_model=os.environ.get("ANDROID_AGENT_OLLAMA_MODEL", "llama3.1"),
            ollama_host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
            runner=os.environ.get("ANDROID_AGENT_RUNNER", "local"),
        )
