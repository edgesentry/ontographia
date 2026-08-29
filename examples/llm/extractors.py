"""Provider-agnostic Intent extractors for local E2E demos."""

from __future__ import annotations

import os
from typing import Any, Protocol, runtime_checkable

from llm.fixtures import MOCK_LLM_INTENTS
from llm.openai_compat import OpenAICompatibleExtractor


@runtime_checkable
class IntentExtractor(Protocol):
    """Extract ontology-constrained Intent JSON from a natural-language question."""

    def extract(self, user_question: str, intent_json_schema: dict[str, Any]) -> dict[str, Any]:
        ...


class MockIntentExtractor:
    """Deterministic fixture-based extractor (CI-safe, no network)."""

    def __init__(self, fixtures: dict[str, dict[str, Any]] | None = None) -> None:
        self._fixtures = fixtures if fixtures is not None else MOCK_LLM_INTENTS

    def extract(self, user_question: str, intent_json_schema: dict[str, Any]) -> dict[str, Any]:
        del intent_json_schema
        try:
            return self._fixtures[user_question]
        except KeyError as exc:
            known = ", ".join(f'"{q}"' for q in self._fixtures)
            raise ValueError(
                f"no mock fixture for question: {user_question!r} (known: {known})"
            ) from exc


def create_extractor(
    backend: str | None = None,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    use_json_schema: bool = True,
) -> IntentExtractor:
    """Create an Intent extractor from backend name or environment variables.

    Environment (when ``backend`` is omitted):
      ONTOGRAPHIA_LLM_BACKEND   mock (default) | openai
      OPENAI_API_KEY            required for openai backend
      OPENAI_BASE_URL           default https://api.openai.com/v1
      OPENAI_MODEL              default gpt-4o-mini
    """
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
        return OpenAICompatibleExtractor(
            api_key=key,
            base_url=base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            use_json_schema=use_json_schema,
        )

    raise ValueError(
        f"unknown LLM backend: {resolved!r} (supported: mock, openai)"
    )
