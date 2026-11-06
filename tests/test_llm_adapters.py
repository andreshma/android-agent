"""Tests for the two LLM adapters and the backend factory.

The adapters were previously at 0% coverage (audit M8/L8). We exercise the
request-building and response-parsing paths with fakes — no network, no SDK —
so the structured-output contract is actually verified.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from android_agent.llm import factory, ollama
from android_agent.llm.anthropic_llm import AnthropicLLM
from android_agent.models import Mission, RiskLevel

_PLAN_PAYLOAD = {
    "summary": "Disable one pre-installed app.",
    "steps": [
        {
            "capability": "optimize",
            "human": "Disable the news app",
            "command": ["adb", "shell", "pm", "disable-user", "com.x.news"],
            "risk": "low",
            "reversible": True,
        }
    ],
}
_PLAN_JSON = json.dumps(_PLAN_PAYLOAD)


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #
def test_is_hosted():
    assert factory.is_hosted("anthropic")
    assert factory.is_hosted("Claude")
    assert not factory.is_hosted("ollama")


def test_make_llm_ollama():
    llm = factory.make_llm("ollama", model="m", host="http://h:1")
    assert isinstance(llm, ollama.OllamaLLM)
    assert llm.name == "ollama"


def test_make_llm_unknown_raises():
    with pytest.raises(ValueError, match="unknown LLM backend"):
        factory.make_llm("gpt-9")


# --------------------------------------------------------------------------- #
# Ollama adapter (monkeypatch httpx.post)
# --------------------------------------------------------------------------- #
class _FakeResp:
    def __init__(self, content: str):
        self._content = content

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"message": {"content": self._content}}


def test_ollama_propose_plan_uses_json_mode_and_framing(monkeypatch):
    captured: dict = {}

    def fake_post(url, json, timeout):  # noqa: A002 - mirrors httpx.post signature
        captured["url"] = url
        captured["body"] = json
        return _FakeResp(_PLAN_JSON)

    monkeypatch.setattr(ollama.httpx, "post", fake_post)
    llm = ollama.OllamaLLM(model="m", host="http://host:11434/")
    plan = llm.propose_plan(
        mission=Mission.OPTIMIZE, request="clean it up", device_facts={"packages": ["com.x.news"]}
    )
    assert plan.mission is Mission.OPTIMIZE
    assert plan.steps[0].risk is RiskLevel.LOW
    # JSON mode is requested and the trailing slash on host was stripped.
    assert captured["body"]["format"] == "json"
    assert captured["url"] == "http://host:11434/api/chat"
    # The device facts are wrapped in the untrusted-data block (audit M6); the
    # delimiter now carries a per-call random nonce (audit L3).
    user_msg = captured["body"]["messages"][1]["content"]
    assert "<device_facts " in user_msg
    assert "untrusted data" in user_msg


def test_ollama_explain_plain_text(monkeypatch):
    def fake_post(url, json, timeout):  # noqa: A002 - mirrors httpx.post signature
        return _FakeResp("in plain words")

    monkeypatch.setattr(ollama.httpx, "post", fake_post)
    llm = ollama.OllamaLLM()
    assert llm.explain("ro.build=foo") == "in plain words"


# --------------------------------------------------------------------------- #
# Anthropic adapter (inject a fake client, no SDK required)
# --------------------------------------------------------------------------- #
def _make_anthropic(msg) -> AnthropicLLM:
    """Build an AnthropicLLM without running __init__ (which imports the SDK)."""
    llm = AnthropicLLM.__new__(AnthropicLLM)
    llm.model = "claude-test"
    llm._client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: msg))
    return llm


def _msg(content, stop_reason="tool_use"):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


def test_anthropic_propose_plan_parses_tool_use():
    block = SimpleNamespace(type="tool_use", name="emit_plan", input=_PLAN_PAYLOAD)
    llm = _make_anthropic(_msg([block]))
    plan = llm.propose_plan(mission=Mission.OPTIMIZE, request="clean", device_facts={})
    assert plan.steps[0].command[-1] == "com.x.news"
    assert plan.steps[0].risk is RiskLevel.LOW


def test_anthropic_rejects_truncated_plan():
    block = SimpleNamespace(type="tool_use", name="emit_plan", input=_PLAN_PAYLOAD)
    llm = _make_anthropic(_msg([block], stop_reason="max_tokens"))
    with pytest.raises(RuntimeError, match="max_tokens"):
        llm.propose_plan(mission=Mission.OPTIMIZE, request="clean", device_facts={})


def test_anthropic_missing_tool_call_raises():
    text = SimpleNamespace(type="text", text="I refuse")
    llm = _make_anthropic(_msg([text]))
    with pytest.raises(RuntimeError, match="emit_plan"):
        llm.propose_plan(mission=Mission.OPTIMIZE, request="clean", device_facts={})


def test_anthropic_explain_joins_text_blocks():
    blocks = [
        SimpleNamespace(type="text", text="part one "),
        SimpleNamespace(type="tool_use", name="x", input={}),
        SimpleNamespace(type="text", text="part two"),
    ]
    llm = _make_anthropic(_msg(blocks))
    assert llm.explain("raw") == "part one part two"
