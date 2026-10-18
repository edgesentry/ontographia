"""Unit checks for execution → Intent refinement (issue #46)."""

from __future__ import annotations

import copy
from typing import Any

from llm.eval.gold import build_gold_cases
from ontographia.llm.exec_feedback import assess_execution, format_execution_feedback
from ontographia.llm.pipeline import (
    ExtractOutcome,
    extract_validated_intent,
    refine_intent_after_execution,
)


def test_assess_empty_and_error() -> None:
    empty = assess_execution(rows=[])
    assert empty.needs_refine and empty.reason == "empty_result"

    err = assess_execution(error=RuntimeError("boom"))
    assert err.needs_refine and err.reason == "neo4j_error"

    ok = assess_execution(rows=[{"plant_name": "Nagoya Plant"}])
    assert ok.ok and ok.row_count == 1

    text = format_execution_feedback(empty, user_question="q")
    assert text.startswith("Neo4j execution feedback")
    assert "Cypher" in text


def test_refine_on_empty_then_success(
    manufacturing_engine, manufacturing_schema, manufacturing_ontology
) -> None:
    case = next(c for c in build_gold_cases() if c.id == "line_plant_00")
    good = case.intent

    class CorrectingExtractor:
        def __init__(self) -> None:
            self.corrections = 0

        def extract(
            self,
            user_question: str,
            intent_json_schema: dict[str, Any],
            *,
            ontology: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            del user_question, intent_json_schema, ontology
            return copy.deepcopy(good)

        def extract_correction(
            self,
            user_question: str,
            intent_json_schema: dict[str, Any],
            *,
            ontology: dict[str, Any] | None,
            previous_intent: dict[str, Any],
            error: str,
        ) -> dict[str, Any]:
            del user_question, intent_json_schema, ontology, previous_intent
            self.corrections += 1
            assert error.startswith("Neo4j execution feedback")
            assert "Do not output Cypher" in error or "not Cypher" in error.lower()
            return copy.deepcopy(good)

    extractor = CorrectingExtractor()
    outcome = extract_validated_intent(
        manufacturing_engine,
        extractor,
        case.question,
        manufacturing_schema,
        ontology=manufacturing_ontology,
        schema_policy="full",
        max_retries=1,
    )

    calls = {"n": 0}

    def execute_fn(built: dict[str, Any]) -> list[dict[str, Any]]:
        del built
        calls["n"] += 1
        if calls["n"] == 1:
            return []
        return [{"plant_name": "Nagoya Plant"}]

    refined = refine_intent_after_execution(
        manufacturing_engine,
        extractor,
        case.question,
        manufacturing_schema,
        outcome,
        execute_fn=execute_fn,
        ontology=manufacturing_ontology,
        max_exec_refines=2,
    )
    assert extractor.corrections == 1
    assert refined.exec_refine_attempts == 1
    assert refined.execution_ok is True
    assert refined.execution_row_count == 1
    assert calls["n"] == 2
    assert "MATCH" in refined.result["query"] or "match" in refined.result["query"].lower()


def test_refine_disabled_when_max_zero(
    manufacturing_engine, manufacturing_schema, manufacturing_ontology
) -> None:
    case = next(c for c in build_gold_cases() if c.id == "line_plant_00")

    class NoCorrectionNeeded:
        def extract(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            del args, kwargs
            return copy.deepcopy(case.intent)

        def extract_correction(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            raise AssertionError("should not correct when max_exec_refines=0")

    outcome = ExtractOutcome(
        intent=case.intent,
        result=manufacturing_engine.build(case.intent),
        schema_mode="full",
        used_fallback=False,
    )
    refined = refine_intent_after_execution(
        manufacturing_engine,
        NoCorrectionNeeded(),
        case.question,
        manufacturing_schema,
        outcome,
        execute_fn=lambda _built: [],
        ontology=manufacturing_ontology,
        max_exec_refines=0,
    )
    assert refined.execution_ok is False
    assert refined.exec_refine_attempts == 0
