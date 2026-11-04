"""Local LLM backend via Ollama.

Default backend: the device's data never leaves the machine, which matters when
auditing a phone. Talks to a local Ollama server over HTTP.

It calls Ollama's /api/chat endpoint with ``format="json"`` and parses the
response into a ``Plan`` via the shared ``schema`` module.
"""

from __future__ import annotations

import httpx

from ..models import Mission, Plan
from . import schema
from .base import LLM, SYSTEM_PROMPT


class OllamaLLM(LLM):
    name = "ollama"

    def __init__(self, model: str = "llama3.1", host: str = "http://localhost:11434") -> None:
        self.model = model
        self.host = host.rstrip("/")

    def _chat(self, user: str, *, json_mode: bool = False) -> str:
        body: dict = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            # Ollama constrains the output to valid JSON when format="json".
            body["format"] = "json"
        resp = httpx.post(f"{self.host}/api/chat", json=body, timeout=120.0)
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    def propose_plan(self, *, mission: Mission, request: str, device_facts: dict) -> Plan:
        prompt = schema.build_user_prompt(mission, request, device_facts)
        raw = self._chat(prompt, json_mode=True)
        return schema.plan_from_text(raw, mission)

    def explain(self, text: str) -> str:
        return self._chat(f"Explain this device output in plain language:\n\n{text}")
