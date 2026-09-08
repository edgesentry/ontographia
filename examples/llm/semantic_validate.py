"""Semantic checks on LLM Intent JSON before Cypher generation (mapping-driven)."""

from __future__ import annotations

from typing import Any

from llm.mapping_loader import default_manufacturing_mapping, load_repair_mapping
from llm.repair import _filter_value, _has_filter, _match_pattern, _resolve_mapping


def semantic_validate_intent(
    question: str,
    intent: dict[str, Any],
    *,
    mapping: dict[str, Any] | None = None,
    mapping_path: str | None = None,
) -> None:
    """Raise ValueError when the Intent likely misses constraints stated in the question."""
    rules = _resolve_mapping(mapping=mapping, mapping_path=mapping_path)
    errors: list[str] = []
    filters = list(intent.get("filter") or [])

    for pattern in rules.get("entity_patterns") or []:
        hit = _match_pattern(question, pattern)
        if hit is None:
            continue
        req = pattern.get("require_filter") or {}
        value = _filter_value(pattern, hit)
        if value is None:
            continue
        if not _has_filter(filters, req, value):
            alias = req.get("alias", "?")
            prop = req.get("property", "?")
            op = req.get("op", "eq")
            pattern_id = pattern.get("id") or pattern.get("match")
            errors.append(
                f"Question matches pattern {pattern_id!r} "
                f"but filter[] does not include "
                f'{{"alias":"{alias}","property":"{prop}","op":"{op}","value":"{value}"}}'
            )

    defaults = rules.get("defaults") or {}
    if defaults.get("fill_as_name", True):
        for item in intent.get("return") or []:
            if item.get("property") and not item.get("as_name"):
                errors.append(
                    f'return item alias={item.get("alias")!r} must include as_name '
                    f"when property is set"
                )

    if errors:
        raise ValueError("; ".join(errors))


# Re-export helpers for tests / callers that load custom mappings.
__all__ = [
    "semantic_validate_intent",
    "default_manufacturing_mapping",
    "load_repair_mapping",
]
