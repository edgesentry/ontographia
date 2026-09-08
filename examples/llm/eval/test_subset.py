"""Unit checks for exact-match ontology subsetting (issue #45).

Run from repo root:
  uv run python examples/llm/eval/test_subset.py
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "examples"
sys.path.insert(0, str(EXAMPLES))

from llm.eval.distractor import generate_distractor_ontology  # noqa: E402
from llm.eval.gold import build_gold_cases  # noqa: E402
from llm.eval.metrics import approx_tokens  # noqa: E402
from llm.pipeline import extract_validated_intent  # noqa: E402
from llm.prompt import build_initial_user_message  # noqa: E402
from llm.subset import (  # noqa: E402
    filter_intent_schema,
    prompt_views_for_question,
    subset_ontology,
    tokenize_question,
)


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def test_tokenize_and_exact_match() -> None:
    tokens = tokenize_question("Which plant hosts production Line-1?")
    _assert("plant" in tokens, f"expected plant in {tokens}")
    _assert("line" in tokens, f"expected line in {tokens}")
    _assert("1" in tokens, f"expected 1 in {tokens}")


def test_manufacturing_subset_keeps_line_plant_edge() -> None:
    import ontographia

    engine = ontographia.Engine.load(str(EXAMPLES / "manufacturing.native.yaml"))
    ontology = engine.ontology_json()
    schema = engine.intent_json_schema()
    question = "Which plant hosts production Line-1?"

    subset = subset_ontology(ontology, question)
    _assert("Plant" in subset.class_names, subset.stats)
    _assert("Line" in subset.class_names, subset.stats)
    _assert("located_at" in subset.relationship_names, subset.stats)
    # Near-duplicate distractors are not present on base ontology; CustomField absent.
    _assert(
        "PlantName" not in subset.property_names,
        f"unexpected props {subset.property_names}",
    )

    filtered_schema, filtered_ont, _ = prompt_views_for_question(
        question, schema, ontology
    )
    class_enum = filtered_schema["$defs"]["NodeRef"]["properties"]["class"]["enum"]
    _assert(set(class_enum) == {"Line", "Plant"}, class_enum)
    _assert(len(filtered_ont["properties"]) <= len(ontology["properties"]), "props grew")


def test_subset_excludes_distractors_and_shrinks_prompt() -> None:
    import ontographia

    yaml_bytes, stats = generate_distractor_ontology("large")
    engine = ontographia.Engine.from_bytes(yaml_bytes, "manufacturing.native.yaml")
    ontology = engine.ontology_json()
    schema = engine.intent_json_schema()
    question = "Which plant hosts production Line-1?"

    subset = subset_ontology(ontology, question)
    _assert(not subset.empty, subset.stats)
    _assert("PlantName" not in subset.property_names, subset.property_names)
    for prop in subset.ontology["properties"]:
        name = str(prop["name"])
        _assert(not name.startswith("CustomField_"), name)
        _assert(name not in {"PlantName", "plant_name", "LineName"}, name)

    full_msg = build_initial_user_message(question, schema, ontology=ontology)
    sub_schema, sub_ont, _ = prompt_views_for_question(question, schema, ontology)
    sub_msg = build_initial_user_message(question, sub_schema, ontology=sub_ont)

    full_tok = approx_tokens(full_msg)
    sub_tok = approx_tokens(sub_msg)
    _assert(sub_tok < full_tok, f"subset {sub_tok} should be < full {full_tok}")
    # Large full prompt is ~13k tokens; subset should drop by an order of magnitude.
    _assert(sub_tok * 5 < full_tok, f"expected large shrink: subset={sub_tok} full={full_tok}")
    _assert(stats["properties"] >= 2000, stats)


def test_filter_schema_preserves_original() -> None:
    schema = {
        "$defs": {
            "NodeRef": {"properties": {"class": {"type": "string", "enum": ["A", "B", "C"]}}},
            "TraverseStep": {
                "properties": {"relationship": {"type": "string", "enum": ["r1", "r2"]}}
            },
        }
    }
    original = copy.deepcopy(schema)
    filtered = filter_intent_schema(schema, class_names=["A"], relationship_names=["r1"])
    _assert(schema == original, "filter mutated input")
    _assert(filtered["$defs"]["NodeRef"]["properties"]["class"]["enum"] == ["A"], filtered)


def test_pipeline_fallback_to_full() -> None:
    import ontographia

    engine = ontographia.Engine.load(str(EXAMPLES / "manufacturing.native.yaml"))
    schema = engine.intent_json_schema()
    ontology = engine.ontology_json()
    case = next(c for c in build_gold_cases() if c.id == "line_plant_00")
    question = case.question
    good = case.intent

    class FlippingExtractor:
        def __init__(self) -> None:
            self.modes: list[str] = []

        def extract(
            self,
            user_question: str,
            intent_json_schema: dict[str, Any],
            *,
            ontology: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            del user_question, ontology
            enums = (
                intent_json_schema.get("$defs", {})
                .get("NodeRef", {})
                .get("properties", {})
                .get("class", {})
                .get("enum")
                or []
            )
            mode = "subset" if len(enums) < 5 else "full"
            self.modes.append(mode)
            if mode == "subset":
                bad = copy.deepcopy(good)
                # Survive manufacturing repair_intent (which rewrites Line-* starts).
                bad["return"] = [
                    {
                        "alias": "plant",
                        "property": "not_a_real_property",
                        "as_name": "x",
                    }
                ]
                return bad
            return copy.deepcopy(good)

    extractor = FlippingExtractor()
    outcome = extract_validated_intent(
        engine,
        extractor,
        question,
        schema,
        ontology=ontology,
        schema_policy="auto",
        max_retries=1,
    )
    _assert(outcome.used_fallback, "expected full-schema fallback")
    _assert(outcome.schema_mode == "full", outcome.schema_mode)
    _assert(extractor.modes == ["subset", "full"], extractor.modes)
    _assert(outcome.intent["start"]["class"] == "Line", outcome.intent)


def main() -> int:
    tests = [
        test_tokenize_and_exact_match,
        test_manufacturing_subset_keeps_line_plant_edge,
        test_subset_excludes_distractors_and_shrinks_prompt,
        test_filter_schema_preserves_original,
        test_pipeline_fallback_to_full,
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
