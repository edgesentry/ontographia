"""Semantic checks on LLM Intent JSON before Cypher generation."""

from __future__ import annotations

import re
from typing import Any


def semantic_validate_intent(question: str, intent: dict[str, Any]) -> None:
    """Raise ValueError when the Intent likely misses constraints stated in the question."""
    errors: list[str] = []
    filters = intent.get("filter", [])
    filter_values = {str(f.get("value", "")) for f in filters}
    filter_values_lower = {v.lower() for v in filter_values}
    question_lower = question.lower()

    sku_match = re.search(r"\bSKU\s+([A-Z0-9-]+)\b", question, re.IGNORECASE)
    if sku_match:
        sku = sku_match.group(1)
        if sku.lower() not in filter_values_lower:
            errors.append(
                f"Question names product SKU {sku!r} but filter[] does not include "
                f'{{"alias":"product","property":"sku","op":"eq","value":"{sku}"}}'
            )

    line_match = re.search(r"\b(Line-\d+)\b", question, re.IGNORECASE)
    if line_match:
        line_name = line_match.group(1)
        if line_name.lower() not in filter_values_lower:
            errors.append(
                f"Question names line {line_name!r} but filter[] does not constrain line.name"
            )

    if "quarantine" in question_lower:
        has_status = any(
            str(f.get("property")) == "status"
            and str(f.get("value", "")).lower() == "quarantine"
            for f in filters
        )
        if not has_status:
            errors.append(
                'Question asks about quarantined lots but filter[] does not include '
                '{"alias":"lot","property":"status","op":"eq","value":"quarantine"}'
            )

    lot_match = re.search(r"\b(LOT-\d{4}-\d{3})\b", question, re.IGNORECASE)
    if lot_match:
        lot_id = lot_match.group(1)
        if lot_id.lower() not in filter_values_lower:
            errors.append(
                f"Question names lot {lot_id!r} but filter[] does not constrain lot.lot_id"
            )

    for item in intent.get("return", []):
        if item.get("property") and not item.get("as_name"):
            errors.append(
                f'return item alias={item.get("alias")!r} must include as_name when property is set'
            )

    if errors:
        raise ValueError("; ".join(errors))
