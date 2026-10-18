"""Provider-agnostic Intent extractors built on :class:`LLMBackend`."""

from __future__ import annotations

import json
import os
from typing import Any, Protocol, runtime_checkable

from ontographia.llm.backend import LLMBackend, OpenAICompatibleBackend
from ontographia.llm.fixtures import MOCK_LLM_INTENTS
from ontographia.llm.prompt import (
    SYSTEM_PROMPT,
    build_correction_message,
    build_initial_user_message,
)


@runtime_checkable
class IntentExtractor(Protocol):
    """Extract ontology-constrained Intent JSON from a natural-language question."""

    def extract(
        self,
        user_question: str,
        intent_json_schema: dict[str, Any],
        *,
        ontology: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...


class MockIntentExtractor:
    """Deterministic fixture-based extractor (CI-safe, no network)."""

    def __init__(self, fixtures: dict[str, dict[str, Any]] | None = None) -> None:
        self._fixtures = fixtures if fixtures is not None else MOCK_LLM_INTENTS

    def extract(
        self,
        user_question: str,
        intent_json_schema: dict[str, Any],
        *,
        ontology: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del intent_json_schema, ontology
        try:
            return self._fixtures[user_question]
        except KeyError as exc:
            known = ", ".join(f'"{q}"' for q in self._fixtures)
            raise ValueError(
                f"no mock fixture for question: {user_question!r} (known: {known})"
            ) from exc


class IntentExtractorClient:
    """Prompt + schema Intent extractor over a pluggable :class:`LLMBackend`."""

    def __init__(
        self,
        backend: LLMBackend,
        *,
        use_json_schema: bool = True,
    ) -> None:
        self._backend = backend
        self._use_json_schema = use_json_schema

    def extract(
        self,
        user_question: str,
        intent_json_schema: dict[str, Any],
        *,
        ontology: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        user_message = build_initial_user_message(
            user_question,
            intent_json_schema,
            ontology=ontology,
        )
        return self._chat(
            [{"role": "user", "content": user_message}],
            intent_json_schema,
        )

    def extract_correction(
        self,
        user_question: str,
        intent_json_schema: dict[str, Any],
        *,
        ontology: dict[str, Any] | None,
        previous_intent: dict[str, Any],
        error: str,
    ) -> dict[str, Any]:
        messages = [
            {
                "role": "user",
                "content": build_initial_user_message(
                    user_question,
                    intent_json_schema,
                    ontology=ontology,
                ),
            },
            {
                "role": "assistant",
                "content": json.dumps(previous_intent, ensure_ascii=False),
            },
            {
                "role": "user",
                "content": build_correction_message(user_question, previous_intent, error),
            },
        ]
        return self._chat(messages, intent_json_schema)

    def _chat(
        self,
        messages: list[dict[str, str]],
        intent_json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        full_messages = [{"role": "system", "content": SYSTEM_PROMPT}, *messages]
        schema = intent_json_schema if self._use_json_schema else None
        result = self._backend.complete(full_messages, json_schema=schema)
        if isinstance(result, dict):
            return result
        # Text backends (or prompt-only fallbacks) return a string.
        from ontographia.llm.backend import _parse_json_object

        return _parse_json_object(result)


def create_extractor(
    backend: str | LLMBackend | IntentExtractor | None = None,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    use_json_schema: bool = True,
) -> IntentExtractor:
    """Create an Intent extractor from a backend name, object, or environment.

    Environment (when ``backend`` is omitted):
      ONTOGRAPHIA_LLM_BACKEND   mock (default) | openai
      OPENAI_API_KEY            required for openai backend
      OPENAI_BASE_URL           default https://api.openai.com/v1
      OPENAI_MODEL              default gpt-4o-mini

    Pass an :class:`LLMBackend` instance to use a custom transport, or any
    object that already implements :class:`IntentExtractor`.
    """
    if backend is not None and not isinstance(backend, str):
        if isinstance(backend, IntentExtractor) and not isinstance(backend, LLMBackend):
            return backend  # type: ignore[return-value]
        if isinstance(backend, LLMBackend):
            return IntentExtractorClient(backend, use_json_schema=use_json_schema)
        # Duck-typed IntentExtractor (has extract)
        if hasattr(backend, "extract"):
            return backend  # type: ignore[return-value]
        raise TypeError(
            "backend must be a str, LLMBackend, or IntentExtractor-like object"
        )

    resolved = (backend or os.environ.get("ONTOGRAPHIA_LLM_BACKEND", "mock")).lower()

    if resolved == "mock":
        return MockIntentExtractor()

    if resolved in {"openai", "openai_compat", "openai-compatible"}:
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError(
                "OPENAI_API_KEY is required for the openai backend "
                "(any OpenAI-compatible endpoint: OpenAI, Ollama, vLLM, LiteLLM proxy, …)"
            )
        llm = OpenAICompatibleBackend(
            api_key=key,
            base_url=base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            use_json_schema=use_json_schema,
        )
        return IntentExtractorClient(llm, use_json_schema=use_json_schema)

    raise ValueError(
        f"unknown LLM backend: {resolved!r} (supported: mock, openai)"
    )
