"""Unit checks for execution → Intent refinement (issue #46).

Run from repo root:
  uv run python examples/llm/eval/test_exec_feedback.py
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "examples"
sys.path.insert(0, str(EXAMPLES))

from llm.eval.gold import build_gold_cases  # noqa: E402
from llm.exec_feedback import assess_execution, format_execution_feedback  # noqa: E402
from llm.pipeline import (  # noqa: E402
    ExtractOutcome,
    extract_validated_intent,
    refine_intent_after_execution,
)


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def test_assess_empty_and_error() -> None:
    empty = assess_execution(rows=[])
    _assert(empty.needs_refine and empty.reason == "empty_result", empty)

    err = assess_execution(error=RuntimeError("boom"))
    _assert(err.needs_refine and err.reason == "neo4j_error", err)

    ok = assess_execution(rows=[{"plant_name": "Nagoya Plant"}])
    _assert(ok.ok and ok.row_count == 1, ok)

    text = format_execution_feedback(empty, user_question="q")
    _assert(text.startswith("Neo4j execution feedback"), text)
    _assert("Cypher" in text, text)


def test_refine_on_empty_then_success() -> None:
    import ontographia

    engine = ontographia.Engine.load(str(EXAMPLES / "manufacturing.native.yaml"))
    schema = engine.intent_json_schema()
    ontology = engine.ontology_json()
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
            _assert(error.startswith("Neo4j execution feedback"), error)
            _assert("Do not output Cypher" in error or "not Cypher" in error.lower(), error)
            return copy.deepcopy(good)

    extractor = CorrectingExtractor()
    outcome = extract_validated_intent(
        engine,
        extractor,
        case.question,
        schema,
        ontology=ontology,
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
        engine,
        extractor,
        case.question,
        schema,
        outcome,
        execute_fn=execute_fn,
        ontology=ontology,
        max_exec_refines=2,
    )
    _assert(extractor.corrections == 1, extractor.corrections)
    _assert(refined.exec_refine_attempts == 1, refined.exec_refine_attempts)
    _assert(refined.execution_ok is True, refined)
    _assert(refined.execution_row_count == 1, refined)
    _assert(calls["n"] == 2, calls)
    _assert(
        "MATCH" in refined.result["query"] or "match" in refined.result["query"].lower(),
        refined.result,
    )


def test_refine_disabled_when_max_zero() -> None:
    import ontographia

    engine = ontographia.Engine.load(str(EXAMPLES / "manufacturing.native.yaml"))
    schema = engine.intent_json_schema()
    ontology = engine.ontology_json()
    case = next(c for c in build_gold_cases() if c.id == "line_plant_00")

    class NoCorrectionNeeded:
        def extract(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            del args, kwargs
            return copy.deepcopy(case.intent)

        def extract_correction(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            raise AssertionError("should not correct when max_exec_refines=0")

    outcome = ExtractOutcome(
        intent=case.intent,
        result=engine.build(case.intent),
        schema_mode="full",
        used_fallback=False,
    )
    refined = refine_intent_after_execution(
        engine,
        NoCorrectionNeeded(),
        case.question,
        schema,
        outcome,
        execute_fn=lambda _built: [],
        ontology=ontology,
        max_exec_refines=0,
    )
    _assert(refined.execution_ok is False, refined)
    _assert(refined.exec_refine_attempts == 0, refined)


def main() -> int:
    tests = [
        test_assess_empty_and_error,
        test_refine_on_empty_then_success,
        test_refine_disabled_when_max_zero,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"ok  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}", file=sys.stderr)
    if failed:
        print(f"{failed}/{len(tests)} failed", file=sys.stderr)
        return 1
    print(f"all {len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
