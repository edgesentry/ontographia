"""Shared prompt text for Intent extraction."""

from __future__ import annotations

import json
import re
from typing import Any

from llm.fixtures import MOCK_LLM_INTENTS

SYSTEM_PROMPT = """\
You translate natural-language graph exploration questions into Ontographia Intent JSON.

Rules:
- Output ONLY valid JSON matching the provided JSON Schema.
- Never output Cypher, SQL, GQL, or any query language.
- Use ONLY class and relationship names from the allowed vocabulary (exact PascalCase / snake_case).
- Do NOT invent synonyms (e.g. use Line, not production_line; use Plant, not plant; use located_at, not located_in).
- If the answer is on a related node, you MUST add a traverse step and define that node in traverse[].to.
- Every return[].alias must be start.alias or a traverse[].to.alias from the same Intent.
- return[].property must be a single property name (e.g. "name"), never a phrase.
- return[] entries that read a property must include property and as_name.
- When the question names a specific entity (SKU, lot_id, line name, status), you MUST add a matching filter[] entry.
- Use filter operators: eq, neq, lt, lte, gt, gte, in, contains.
- Include "limit": 20 unless the question specifies otherwise.
- For multi-level BOM (sub-assemblies), insert a has_sub_part traverse between has_part and supplied_by.
"""

EXAMPLE_LINE_PLANT = MOCK_LLM_INTENTS["Which plant hosts production Line-1?"]
EXAMPLE_BOM_SUPPLIERS = MOCK_LLM_INTENTS["List suppliers for parts in product SKU SPX-100"]
EXAMPLE_LOT_DEFECT = MOCK_LLM_INTENTS["Which defect codes affect quarantined lots?"]


def pick_example_intent(question: str) -> dict[str, Any]:
    q = question.lower()
    if "supplier" in q or "sku" in q or "bom" in q or "part" in q and "product" in q:
        return EXAMPLE_BOM_SUPPLIERS
    if "defect" in q or "quarantine" in q:
        return EXAMPLE_LOT_DEFECT
    if "line" in q or "plant" in q:
        return EXAMPLE_LINE_PLANT
    return EXAMPLE_LINE_PLANT


def example_label(question: str) -> str:
    example = pick_example_intent(question)
    if example is EXAMPLE_BOM_SUPPLIERS:
        return "product→part→supplier (with SKU filter)"
    if example is EXAMPLE_LOT_DEFECT:
        return "lot→defect (with status filter)"
    return "line→plant (with name filter)"


def vocabulary_from_schema(intent_json_schema: dict[str, Any]) -> str:
    lines: list[str] = []
    defs = intent_json_schema.get("$defs", {})

    classes = defs.get("NodeRef", {}).get("properties", {}).get("class", {}).get("enum")
    if classes:
        lines.append(f"Allowed classes (exact names): {', '.join(classes)}")

    relationships = defs.get("TraverseStep", {}).get("properties", {}).get("relationship", {}).get("enum")
    if relationships:
        lines.append(f"Allowed relationships: {', '.join(relationships)}")

    return "\n".join(lines)


def properties_from_ontology(ontology: dict[str, Any]) -> str:
    by_class: dict[str, set[str]] = {}
    for prop in ontology.get("properties", []):
        owner = prop.get("owner_class")
        name = prop.get("name")
        if owner and name:
            by_class.setdefault(str(owner), set()).add(str(name))
    if not by_class:
        return ""
    lines = ["Properties per class:"]
    for cls in sorted(by_class):
        lines.append(f"  {cls}: {', '.join(sorted(by_class[cls]))}")
    return "\n".join(lines)


def build_initial_user_message(
    user_question: str,
    intent_json_schema: dict[str, Any],
    *,
    ontology: dict[str, Any] | None = None,
) -> str:
    parts = [f"User question:\n{user_question}"]
    vocabulary = vocabulary_from_schema(intent_json_schema)
    if vocabulary:
        parts.append(f"Ontology vocabulary:\n{vocabulary}")
    if ontology:
        property_vocab = properties_from_ontology(ontology)
        if property_vocab:
            parts.append(property_vocab)
    example = pick_example_intent(user_question)
    parts.append(
        f"Example Intent JSON ({example_label(user_question)}):\n"
        f"{json.dumps(example, indent=2)}"
    )
    parts.append(f"JSON Schema for Intent:\n{json.dumps(intent_json_schema, indent=2)}")
    return "\n\n".join(parts)


def build_correction_message(previous_intent: dict[str, Any], error: str) -> str:
    return (
        "Your previous Intent JSON failed validation.\n"
        f"Error: {error}\n\n"
        f"Previous JSON:\n{json.dumps(previous_intent, indent=2)}\n\n"
        "Return a corrected Intent JSON only. Ensure:\n"
        "- traverse defines every return alias that is not start.alias\n"
        "- filter[] includes every specific entity named in the question (SKU, line name, lot_id, status)\n"
        "- each return item with property also has as_name"
    )
