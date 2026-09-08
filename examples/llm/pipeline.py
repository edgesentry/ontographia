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
DEFAULT_INITIAL_RETRIES = 1
DEFAULT_ESCALATED_RETRIES = DEFAULT_MAX_RETRIES
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
    llm_calls: int = 0
    phases_tried: tuple[str, ...] = ()
    retries_budget_used: int = 0
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
    max_retries: int | None = None,
    initial_retries: int = DEFAULT_INITIAL_RETRIES,
    escalated_retries: int = DEFAULT_ESCALATED_RETRIES,
    schema_policy: SchemaPolicy = "auto",
    repair_mapping: dict[str, Any] | None = None,
    repair_mapping_path: str | None = None,
) -> ExtractOutcome:
    """Extract Intent JSON, retrying with validation feedback when invalid.

    ``schema_policy``:
      - ``auto`` (default): try exact-match ontology subset first with a small
        retry budget; on failure, escalate to full schema and more retries
        (issues #45 / #47 difficulty-adaptive spend).
      - ``subset``: subset only (no fallback; for evaluation).
      - ``full``: full schema only.

    Retry budgets (issue #47):
      - subset phase uses ``initial_retries`` (default 1)
      - full / escalate phase uses ``escalated_retries`` (default 5)
      - ``max_retries``, if set, overrides both budgets (legacy / eval pin)
    """
    if max_retries is not None:
        if max_retries < 1:
            raise ValueError("max_retries must be >= 1")
        initial_retries = max_retries
        escalated_retries = max_retries
    if initial_retries < 1:
        raise ValueError("initial_retries must be >= 1")
    if escalated_retries < 1:
        raise ValueError("escalated_retries must be >= 1")

    phases = _schema_phases(
        user_question,
        intent_json_schema,
        ontology,
        schema_policy=schema_policy,
    )
    last_error = "unknown validation error"
    used_fallback = False
    llm_calls = 0
    phases_tried: list[str] = []
    retries_budget_used = 0

    for phase_idx, phase in enumerate(phases):
        if phase_idx > 0:
            used_fallback = True
        budget = (
            initial_retries if phase["mode"] == "subset" else escalated_retries
        )
        phases_tried.append(phase["mode"])
        try:
            intent, result, calls = _extract_with_schema(
                engine,
                extractor,
                user_question,
                phase["schema"],
                ontology=phase["ontology"],
                dialect=dialect,
                max_retries=budget,
                repair_mapping=repair_mapping,
                repair_mapping_path=repair_mapping_path,
            )
            llm_calls += calls
            retries_budget_used += calls
            return ExtractOutcome(
                intent=intent,
                result=result,
                schema_mode=phase["mode"],
                used_fallback=used_fallback,
                subset_stats=phase.get("subset_stats"),
                llm_calls=llm_calls,
                phases_tried=tuple(phases_tried),
                retries_budget_used=retries_budget_used,
            )
        except Exception as exc:  # noqa: BLE001 - become next-phase / final error
            # Count failed attempts: up to budget extract/correct calls were made.
            # _extract_with_schema raises after exhausting retries; recover call
            # count from the exception attribute when present.
            failed_calls = getattr(exc, "llm_calls", budget)
            llm_calls += int(failed_calls)
            retries_budget_used += int(failed_calls)
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
    repair_mapping: dict[str, Any] | None = None,
    repair_mapping_path: str | None = None,
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
        intent = repair_intent(
            user_question,
            intent,
            mapping=repair_mapping,
            mapping_path=repair_mapping_path,
        )
        try:
            semantic_validate_intent(
                user_question,
                intent,
                mapping=repair_mapping,
                mapping_path=repair_mapping_path,
            )
            result = engine.build(intent, dialect=dialect)
        except Exception as exc:  # noqa: BLE001 - treat as failed refine; stop
            return replace(
                current,
                exec_refine_attempts=attempts,
                execution_ok=False,
                execution_feedback=(
                    f"{feedback}\n\nIntent correction failed validation: {exc}"
                ),
                llm_calls=current.llm_calls + 1,
            )

        current = replace(
            current,
            intent=intent,
            result=result,
            exec_refine_attempts=attempts,
            llm_calls=current.llm_calls + 1,
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


class _ExtractExhausted(ValueError):
    """Validation failed after exhausting retries; carries llm_calls for accounting."""

    def __init__(self, message: str, *, llm_calls: int) -> None:
        super().__init__(message)
        self.llm_calls = llm_calls


def _extract_with_schema(
    engine: Any,
    extractor: Any,
    user_question: str,
    intent_json_schema: dict[str, Any],
    *,
    ontology: dict[str, Any] | None,
    dialect: str,
    max_retries: int,
    repair_mapping: dict[str, Any] | None = None,
    repair_mapping_path: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], int]:
    intent: dict[str, Any] | None = None
    last_error = "unknown validation error"
    llm_calls = 0

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

        llm_calls += 1
        intent = repair_intent(
            user_question,
            intent,
            mapping=repair_mapping,
            mapping_path=repair_mapping_path,
        )

        try:
            semantic_validate_intent(
                user_question,
                intent,
                mapping=repair_mapping,
                mapping_path=repair_mapping_path,
            )
            result = engine.build(intent, dialect=dialect)
            return intent, result, llm_calls
        except Exception as exc:  # noqa: BLE001 - validation errors become LLM feedback
            last_error = str(exc)
            if attempt + 1 >= max_retries:
                raise _ExtractExhausted(last_error, llm_calls=llm_calls) from exc

    raise _ExtractExhausted(last_error, llm_calls=llm_calls)
