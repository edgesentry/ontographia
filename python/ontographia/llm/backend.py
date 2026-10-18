"""Pluggable LLM backends for Intent extraction.

The default implementation talks to any OpenAI-compatible HTTP endpoint via the
official ``openai`` Python SDK (``base_url`` + ``api_key`` + ``model``).
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

ChatMessage = Mapping[str, str]


@runtime_checkable
class LLMBackend(Protocol):
    """Minimal chat-completion backend used by Intent extractors.

    Implementations may return a JSON object (preferred when structured output
    is requested) or a raw assistant text string that the caller will parse.
    """

    def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        json_schema: dict[str, Any] | None = None,
    ) -> str | dict[str, Any]:
        """Run one chat completion.

        ``json_schema``, when provided, requests JSON-schema-constrained output
        where the provider supports it. Backends should fall back to plain JSON
        mode / unconstrained text when the provider rejects ``json_schema``.
        """
        ...


class OpenAICompatibleBackend:
    """Default backend: official ``openai`` SDK against any compatible endpoint.

    Works with OpenAI, Azure OpenAI, Ollama, vLLM, OpenRouter, LiteLLM Proxy,
    and other OpenAI-compatible gateways (including Gemini/Anthropic proxies).
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        use_json_schema: bool = True,
        timeout_s: float = 120.0,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - guarded by package import
            raise ImportError(
                'ontographia.llm requires the optional "llm" extra. '
                'Install with: pip install "ontographia[llm]"'
            ) from exc

        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
            timeout=timeout_s,
        )
        self._model = model
        self._use_json_schema = use_json_schema

    def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload_messages = [{"role": m["role"], "content": m["content"]} for m in messages]

        if json_schema is not None and self._use_json_schema:
            try:
                return self._request(
                    payload_messages,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "ontographia_intent",
                            "schema": json_schema,
                            "strict": True,
                        },
                    },
                )
            except Exception as exc:  # noqa: BLE001 - probe provider capability
                if not _is_schema_unsupported(exc):
                    raise

        if json_schema is not None:
            return self._request(
                payload_messages,
                response_format={"type": "json_object"},
            )

        return self._request(payload_messages, response_format=None)

    def _request(
        self,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": 0,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        try:
            data = self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 - normalize provider errors
            raise ValueError(f"LLM request failed: {exc}") from exc

        content = data.choices[0].message.content
        if not isinstance(content, str):
            raise ValueError(f"unexpected LLM response type: {type(content)!r}")
        return _parse_json_object(content)


def _parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError(f"LLM output must be a JSON object, got {type(parsed)!r}")
    return parsed


def _is_schema_unsupported(exc: BaseException) -> bool:
    """Detect providers that reject ``response_format.json_schema``."""
    status = getattr(exc, "status_code", None)
    if status in {400, 404, 422}:
        return True
    # openai.BadRequestError / APIStatusError often wrap a response
    response = getattr(exc, "response", None)
    if response is not None:
        code = getattr(response, "status_code", None)
        if code in {400, 404, 422}:
            return True
    msg = str(exc).lower()
    if "json_schema" in msg or "response_format" in msg:
        return True
    # Fallback path also triggers when we wrapped as ValueError
    if isinstance(exc, ValueError) and "json_schema" in msg:
        return True
    return False
