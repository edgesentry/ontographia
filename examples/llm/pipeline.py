"""Extract Intent JSON and validate via Ontographia Engine.build()."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, Literal

from llm.exec_feedback import assess_execution, format_execution_feedback
from llm.repair import repair_intent
from llm.semantic_validate import semantic_validate_intent
from llm.subset import prompt_views_for_question

DEFAULT_MAX_RETRIES = 5
DEFAULT_MAX_EXEC_REFINES = 2

SchemaPolicy = Literal["auto", "subset", "full"]

# execute_fn(built_result) -> list[dict] rows; may raise on driver errors
ExecuteFn = Callable[[dict[str, Any]], list[dict[str, Any]]]


@dataclass(frozen=True)
class ExtractOutcome:
    intent: dict[str, Any]
    result: dict[str, Any]
    schema_mode: Literal["subset", "full"]
    used_fallback: bool
    subset_stats: dict[str, int | bool] | None = None
    exec_refine_attempts: int = 0
    execution_ok: bool | None = None
    execution_row_count: int | None = None
    execution_rows: list[dict[str, Any]] | None = None
    execution_feedback: str | None = None


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


def refine_intent_after_execution(
    engine: Any,
    extractor: Any,
    user_question: str,
    intent_json_schema: dict[str, Any],
    outcome: ExtractOutcome,
    *,
    execute_fn: ExecuteFn,
    ontology: dict[str, Any] | None = None,
    dialect: str = "cypher25",
    max_exec_refines: int = DEFAULT_MAX_EXEC_REFINES,
) -> ExtractOutcome:
    """After a successful build, run Neo4j and optionally correct Intent (issue #46).

    On empty results or driver errors, ask the extractor for a corrected Intent
    (never Cypher), then ``Engine.build`` again. Uses the full Intent schema for
    correction prompts so the model can recover from under-selected subsets.
    """
    if max_exec_refines < 0:
        raise ValueError("max_exec_refines must be >= 0")
    if not hasattr(extractor, "extract_correction"):
        return _attach_execution(outcome, execute_fn, user_question)

    current = outcome
    attempts = 0

    while True:
        assessment_rows: list[dict[str, Any]] | None
        assessment_error: BaseException | None
        try:
            assessment_rows = execute_fn(current.result)
            assessment_error = None
        except Exception as exc:  # noqa: BLE001 - becomes Intent feedback
            assessment_rows = None
            assessment_error = exc

        assessment = assess_execution(rows=assessment_rows, error=assessment_error)
        feedback = format_execution_feedback(assessment, user_question=user_question)
        current = replace(
            current,
            execution_ok=assessment.ok,
            execution_row_count=assessment.row_count,
            execution_rows=assessment_rows if assessment_error is None else None,
            execution_feedback=None if assessment.ok else feedback,
            exec_refine_attempts=attempts,
        )

        if assessment.ok or attempts >= max_exec_refines:
            return current

        attempts += 1
        intent = extractor.extract_correction(
            user_question,
            intent_json_schema,
            ontology=ontology,
            previous_intent=current.intent,
            error=feedback,
        )
        intent = repair_intent(user_question, intent)
        try:
            semantic_validate_intent(user_question, intent)
            result = engine.build(intent, dialect=dialect)
        except Exception as exc:  # noqa: BLE001 - treat as failed refine; stop
            return replace(
                current,
                exec_refine_attempts=attempts,
                execution_ok=False,
                execution_feedback=(
                    f"{feedback}\n\nIntent correction failed validation: {exc}"
                ),
            )

        current = replace(
            current,
            intent=intent,
            result=result,
            exec_refine_attempts=attempts,
        )


def _attach_execution(
    outcome: ExtractOutcome,
    execute_fn: ExecuteFn,
    user_question: str,
) -> ExtractOutcome:
    rows: list[dict[str, Any]] | None = None
    try:
        rows = execute_fn(outcome.result)
        assessment = assess_execution(rows=rows)
    except Exception as exc:  # noqa: BLE001
        assessment = assess_execution(error=exc)
    feedback = (
        None
        if assessment.ok
        else format_execution_feedback(assessment, user_question=user_question)
    )
    return replace(
        outcome,
        execution_ok=assessment.ok,
        execution_row_count=assessment.row_count,
        execution_rows=rows,
        execution_feedback=feedback,
        exec_refine_attempts=0,
    )


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
