"""Extract Intent JSON and validate via Ontographia Engine.build()."""

from __future__ import annotations

from typing import Any

from llm.semantic_validate import semantic_validate_intent

DEFAULT_MAX_RETRIES = 3


def extract_validated_intent(
    engine: Any,
    extractor: Any,
    user_question: str,
    intent_json_schema: dict[str, Any],
    *,
    ontology: dict[str, Any] | None = None,
    dialect: str = "cypher25",
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract Intent JSON, retrying with validation feedback when the LLM output is invalid."""
    intent: dict[str, Any] | None = None
    last_error = "unknown validation error"

    for attempt in range(max_retries):
        if attempt == 0:
            try:
                intent = extractor.extract(
                    user_question,
                    intent_json_schema,
                    ontology=ontology,
                )
            except TypeError:
                intent = extractor.extract(user_question, intent_json_schema)
        else:
            if not hasattr(extractor, "extract_correction"):
                break
            intent = extractor.extract_correction(
                user_question,
                intent_json_schema,
                ontology=ontology,
                previous_intent=intent or {},
                error=last_error,
            )

        try:
            semantic_validate_intent(user_question, intent)
            result = engine.build(intent, dialect=dialect)
            return intent, result
        except Exception as exc:  # noqa: BLE001 - validation errors become LLM feedback
            last_error = str(exc)
            if attempt + 1 >= max_retries:
                raise ValueError(last_error) from exc

    raise ValueError(last_error)
