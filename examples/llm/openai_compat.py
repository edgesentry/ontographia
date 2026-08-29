"""OpenAI-compatible chat completions client (stdlib only).

Works with any endpoint that implements POST /v1/chat/completions:
OpenAI, Azure OpenAI, Ollama (http://localhost:11434/v1), vLLM, LiteLLM, etc.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from llm.prompt import (
    SYSTEM_PROMPT,
    build_correction_message,
    build_initial_user_message,
)


class OpenAICompatibleExtractor:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        use_json_schema: bool = True,
        timeout_s: float = 120.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._use_json_schema = use_json_schema
        self._timeout_s = timeout_s

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
        return self._chat([{"role": "user", "content": user_message}], intent_json_schema)

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
        if self._use_json_schema:
            try:
                return self._request(
                    full_messages,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "ontographia_intent",
                            "schema": intent_json_schema,
                            "strict": True,
                        },
                    },
                )
            except (urllib.error.HTTPError, ValueError) as exc:
                if not _is_schema_unsupported(exc):
                    raise

        return self._request(full_messages, response_format={"type": "json_object"})

    def _request(
        self,
        messages: list[dict[str, str]],
        response_format: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": 0,
            "response_format": response_format,
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ValueError(f"LLM HTTP {exc.code}: {detail}") from exc

        content = data["choices"][0]["message"]["content"]
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
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in {400, 404, 422}:
            return True
    if isinstance(exc, ValueError) and "json_schema" in str(exc).lower():
        return True
    return False
