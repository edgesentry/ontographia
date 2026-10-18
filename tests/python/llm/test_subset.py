"""Unit checks for exact-match ontology subsetting (issue #45)."""

from __future__ import annotations

import copy
from typing import Any

from llm.eval.distractor import generate_distractor_ontology
from llm.eval.gold import build_gold_cases
from llm.eval.metrics import approx_tokens
from ontographia.llm.pipeline import extract_validated_intent
from ontographia.llm.prompt import build_initial_user_message
from ontographia.llm.subset import (
    filter_intent_schema,
    prompt_views_for_question,
    subset_ontology,
    tokenize_question,
)



def test_tokenize_and_exact_match() -> None:
    tokens = tokenize_question("Which plant hosts production Line-1?")
    assert "plant" in tokens
    assert "line" in tokens
    assert "1" in tokens


def test_manufacturing_subset_keeps_line_plant_edge(
    manufacturing_engine, manufacturing_schema, manufacturing_ontology
) -> None:
    del manufacturing_engine
    question = "Which plant hosts production Line-1?"

    subset = subset_ontology(manufacturing_ontology, question)
    assert "Plant" in subset.class_names
    assert "Line" in subset.class_names
    assert "located_at" in subset.relationship_names
    assert "PlantName" not in subset.property_names

    filtered_schema, filtered_ont, _ = prompt_views_for_question(
        question, manufacturing_schema, manufacturing_ontology
    )
    class_enum = filtered_schema["$defs"]["NodeRef"]["properties"]["class"]["enum"]
    assert set(class_enum) == {"Line", "Plant"}
    assert len(filtered_ont["properties"]) <= len(manufacturing_ontology["properties"])


def test_subset_excludes_distractors_and_shrinks_prompt() -> None:
    import ontographia

    yaml_bytes, stats = generate_distractor_ontology("large")
    engine = ontographia.Engine.from_bytes(yaml_bytes, "manufacturing.native.yaml")
    ontology = engine.ontology_json()
    schema = engine.intent_json_schema()
    question = "Which plant hosts production Line-1?"

    subset = subset_ontology(ontology, question)
    assert not subset.empty
    assert "PlantName" not in subset.property_names
    for prop in subset.ontology["properties"]:
        name = str(prop["name"])
        assert not name.startswith("CustomField_")
        assert name not in {"PlantName", "plant_name", "LineName"}

    full_msg = build_initial_user_message(question, schema, ontology=ontology)
    sub_schema, sub_ont, _ = prompt_views_for_question(question, schema, ontology)
    sub_msg = build_initial_user_message(question, sub_schema, ontology=sub_ont)

    full_tok = approx_tokens(full_msg)
    sub_tok = approx_tokens(sub_msg)
    assert sub_tok < full_tok
    assert sub_tok * 5 < full_tok
    assert stats["properties"] >= 2000


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
    assert schema == original
    assert filtered["$defs"]["NodeRef"]["properties"]["class"]["enum"] == ["A"]


def test_pipeline_fallback_to_full(
    manufacturing_engine, manufacturing_schema, manufacturing_ontology
) -> None:
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
        manufacturing_engine,
        extractor,
        question,
        manufacturing_schema,
        ontology=manufacturing_ontology,
        schema_policy="auto",
        max_retries=1,
    )
    assert outcome.used_fallback
    assert outcome.schema_mode == "full"
    assert extractor.modes == ["subset", "full"]
    assert outcome.intent["start"]["class"] == "Line"
    assert outcome.llm_calls == 2
    assert outcome.phases_tried == ("subset", "full")


def test_adaptive_success_skips_full_and_limits_retries(
    manufacturing_engine, manufacturing_schema, manufacturing_ontology
) -> None:
    case = next(c for c in build_gold_cases() if c.id == "line_plant_00")

    class CountingExtractor:
        def __init__(self) -> None:
            self.calls = 0
            self.modes: list[str] = []

        def extract(
            self,
            user_question: str,
            intent_json_schema: dict[str, Any],
            *,
            ontology: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            del user_question, ontology
            self.calls += 1
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
            return copy.deepcopy(case.intent)

        def extract_correction(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            del args, kwargs
            raise AssertionError("correction should not run on easy success path")

    extractor = CountingExtractor()
    outcome = extract_validated_intent(
        manufacturing_engine,
        extractor,
        case.question,
        manufacturing_schema,
        ontology=manufacturing_ontology,
        schema_policy="auto",
        initial_retries=1,
        escalated_retries=5,
    )
    assert not outcome.used_fallback
    assert outcome.schema_mode == "subset"
    assert extractor.modes == ["subset"]
    assert extractor.calls == 1
    assert outcome.llm_calls == 1
    assert outcome.phases_tried == ("subset",)


def test_adaptive_escalate_uses_escalated_retry_budget(
    manufacturing_engine, manufacturing_schema, manufacturing_ontology
) -> None:
    case = next(c for c in build_gold_cases() if c.id == "line_plant_00")
    good = case.intent

    class EscalatingExtractor:
        def __init__(self) -> None:
            self.modes: list[str] = []
            self.subset_attempts = 0
            self.full_attempts = 0

        def _mode(self, intent_json_schema: dict[str, Any]) -> str:
            enums = (
                intent_json_schema.get("$defs", {})
                .get("NodeRef", {})
                .get("properties", {})
                .get("class", {})
                .get("enum")
                or []
            )
            return "subset" if len(enums) < 5 else "full"

        def extract(
            self,
            user_question: str,
            intent_json_schema: dict[str, Any],
            *,
            ontology: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            del user_question, ontology
            mode = self._mode(intent_json_schema)
            self.modes.append(mode)
            if mode == "subset":
                self.subset_attempts += 1
                bad = copy.deepcopy(good)
                bad["return"] = [
                    {
                        "alias": "plant",
                        "property": "not_a_real_property",
                        "as_name": "x",
                    }
                ]
                return bad
            self.full_attempts += 1
            if self.full_attempts == 1:
                bad = copy.deepcopy(good)
                bad["return"] = [
                    {
                        "alias": "plant",
                        "property": "still_wrong_property",
                        "as_name": "x",
                    }
                ]
                return bad
            return copy.deepcopy(good)

        def extract_correction(
            self,
            user_question: str,
            intent_json_schema: dict[str, Any],
            *,
            ontology: dict[str, Any] | None = None,
            previous_intent: dict[str, Any] | None = None,
            error: str | None = None,
        ) -> dict[str, Any]:
            del previous_intent, error
            return self.extract(user_question, intent_json_schema, ontology=ontology)

    extractor = EscalatingExtractor()
    outcome = extract_validated_intent(
        manufacturing_engine,
        extractor,
        case.question,
        manufacturing_schema,
        ontology=manufacturing_ontology,
        schema_policy="auto",
        initial_retries=1,
        escalated_retries=3,
    )
    assert outcome.used_fallback
    assert outcome.schema_mode == "full"
    assert extractor.subset_attempts == 1
    assert extractor.full_attempts == 2
    assert outcome.llm_calls == 3
    assert outcome.phases_tried == ("subset", "full")
