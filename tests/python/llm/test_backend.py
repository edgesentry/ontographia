"""Fake LLMBackend tests — no network."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

import pytest

from ontographia.llm.backend import LLMBackend, OpenAICompatibleBackend
from ontographia.llm.extractors import IntentExtractorClient, create_extractor
from ontographia.llm.fixtures import MOCK_LLM_INTENTS


class FakeBackend:
    """Records calls and returns a canned Intent JSON object."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[tuple[list[dict[str, str]], dict[str, Any] | None]] = []

    def complete(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.calls.append(([dict(m) for m in messages], json_schema))
        return dict(self.payload)


def test_fake_backend_satisfies_protocol() -> None:
    backend = FakeBackend(MOCK_LLM_INTENTS["Which plant hosts production Line-1?"])
    assert isinstance(backend, LLMBackend)


def test_intent_extractor_client_uses_backend() -> None:
    intent = MOCK_LLM_INTENTS["Which plant hosts production Line-1?"]
    backend = FakeBackend(intent)
    client = IntentExtractorClient(backend)
    schema = {"type": "object", "properties": {}}
    out = client.extract("Which plant hosts production Line-1?", schema, ontology=None)
    assert out == intent
    assert len(backend.calls) == 1
    messages, json_schema = backend.calls[0]
    assert messages[0]["role"] == "system"
    assert json_schema is schema


def test_create_extractor_accepts_backend_object() -> None:
    intent = MOCK_LLM_INTENTS["Which plant hosts production Line-1?"]
    backend = FakeBackend(intent)
    extractor = create_extractor(backend)
    out = extractor.extract("Which plant hosts production Line-1?", {"type": "object"})
    assert out["start"]["class"] == "Line"


def test_create_extractor_mock() -> None:
    extractor = create_extractor("mock")
    q = "Which plant hosts production Line-1?"
    assert extractor.extract(q, {})["start"]["class"] == "Line"


def test_openai_compatible_backend_requires_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        create_extractor("openai")


def test_openai_compatible_backend_constructs_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Construction must not hit the network; only instantiate the SDK client."""
    created: dict[str, Any] = {}

    class DummyCompletions:
        def create(self, **kwargs: Any) -> Any:
            raise AssertionError("should not call create in this test")

    class DummyChat:
        completions = DummyCompletions()

    class DummyClient:
        def __init__(self, **kwargs: Any) -> None:
            created.update(kwargs)
            self.chat = DummyChat()

    monkeypatch.setattr("openai.OpenAI", DummyClient)
    backend = OpenAICompatibleBackend(
        api_key="sk-test",
        base_url="http://localhost:11434/v1",
        model="llama3.1",
    )
    assert created["api_key"] == "sk-test"
    assert created["base_url"] == "http://localhost:11434/v1"

    # Drive complete() with a stubbed response
    class Msg:
        content = json.dumps({"ok": True})

    class Choice:
        message = Msg()

    class Resp:
        choices = [Choice()]

    def create(**kwargs: Any) -> Resp:
        created["last_kwargs"] = kwargs
        return Resp()

    backend._client.chat.completions.create = create  # type: ignore[method-assign]
    out = backend.complete(
        [{"role": "user", "content": "hi"}],
        json_schema={"type": "object"},
    )
    assert out == {"ok": True}
    assert created["last_kwargs"]["response_format"]["type"] == "json_schema"
