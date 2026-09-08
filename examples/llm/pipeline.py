"""Extract Intent JSON and validate via Ontographia Engine.build()."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from llm.repair import repair_intent
from llm.semantic_validate import semantic_validate_intent
from llm.subset import prompt_views_for_question

DEFAULT_MAX_RETRIES = 5

SchemaPolicy = Literal["auto", "subset", "full"]


@dataclass(frozen=True)
class ExtractOutcome:
    intent: dict[str, Any]
    result: dict[str, Any]
    schema_mode: Literal["subset", "full"]
    used_fallback: bool
    subset_stats: dict[str, int | bool] | None = None


def extract_validated_intent(
    engine: Any,
    extractor: Any,
    user_question: str,
    intent_json_schema: dict[str, Any],
    *,
    ontology: dict[str, Any] | None = None,
    dialect: str = "cypher25",
    max_retries: int = DEFAULT_MAX_RETRIES,
    schema_policy: SchemaPolicy = "auto",
) -> ExtractOutcome:
    """Extract Intent JSON, retrying with validation feedback when invalid.

    ``schema_policy``:
      - ``auto`` (default): try exact-match ontology subset first; on failure,
        fall back to the full Intent schema / ontology vocabulary (issue #45).
      - ``subset``: subset only (no fallback; for evaluation).
      - ``full``: full schema only.
    """
    phases = _schema_phases(
        user_question,
        intent_json_schema,
        ontology,
        schema_policy=schema_policy,
    )
    last_error = "unknown validation error"
    used_fallback = False

    for phase_idx, phase in enumerate(phases):
        if phase_idx > 0:
            used_fallback = True
        try:
            intent, result = _extract_with_schema(
                engine,
                extractor,
                user_question,
                phase["schema"],
                ontology=phase["ontology"],
                dialect=dialect,
                max_retries=max_retries,
            )
            return ExtractOutcome(
                intent=intent,
                result=result,
                schema_mode=phase["mode"],
                used_fallback=used_fallback,
                subset_stats=phase.get("subset_stats"),
            )
        except Exception as exc:  # noqa: BLE001 - become next-phase / final error
            last_error = str(exc)
            if phase_idx + 1 >= len(phases):
                raise ValueError(last_error) from exc

    raise ValueError(last_error)


def _schema_phases(
    user_question: str,
    intent_json_schema: dict[str, Any],
    ontology: dict[str, Any] | None,
    *,
    schema_policy: SchemaPolicy,
) -> list[dict[str, Any]]:
    full = {
        "mode": "full",
        "schema": intent_json_schema,
        "ontology": ontology,
        "subset_stats": None,
    }
    if schema_policy == "full" or ontology is None:
        return [full]

    schema_sub, ont_sub, subset = prompt_views_for_question(
        user_question,
        intent_json_schema,
        ontology,
    )
    if subset.empty:
        return [full]

    subset_phase = {
        "mode": "subset",
        "schema": schema_sub,
        "ontology": ont_sub,
        "subset_stats": subset.stats,
    }
    if schema_policy == "subset":
        return [subset_phase]
    # auto
    return [subset_phase, full]


def _extract_with_schema(
    engine: Any,
    extractor: Any,
    user_question: str,
    intent_json_schema: dict[str, Any],
    *,
    ontology: dict[str, Any] | None,
    dialect: str,
    max_retries: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
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

        intent = repair_intent(user_question, intent)

        try:
            semantic_validate_intent(user_question, intent)
            result = engine.build(intent, dialect=dialect)
            return intent, result
        except Exception as exc:  # noqa: BLE001 - validation errors become LLM feedback
            last_error = str(exc)
            if attempt + 1 >= max_retries:
                raise ValueError(last_error) from exc

    raise ValueError(last_error)
