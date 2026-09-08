"""Deterministic repairs for common LLM Intent omissions (mapping-driven)."""

from __future__ import annotations

import copy
import re
from typing import Any

from llm.mapping_loader import default_manufacturing_mapping, load_repair_mapping

_FLAG_MAP = {
    "IGNORECASE": re.IGNORECASE,
    "MULTILINE": re.MULTILINE,
    "DOTALL": re.DOTALL,
}


def repair_intent(
    question: str,
    intent: dict[str, Any],
    *,
    mapping: dict[str, Any] | None = None,
    mapping_path: str | None = None,
) -> dict[str, Any]:
    """Apply safe, question-driven fixes before semantic/engine validation.

    When ``mapping`` / ``mapping_path`` are omitted, uses the manufacturing
    default YAML (``examples/llm/mappings/manufacturing.repair.yaml``).
    """
    rules = _resolve_mapping(mapping=mapping, mapping_path=mapping_path)
    out = copy.deepcopy(intent)
    filters: list[dict[str, Any]] = list(out.get("filter") or [])

    for pattern in rules.get("entity_patterns") or []:
        hit = _match_pattern(question, pattern)
        if hit is None:
            continue
        req = pattern.get("require_filter") or {}
        value = _filter_value(pattern, hit)
        if value is None:
            continue
        if not _has_filter(filters, req, value):
            filters.append(
                {
                    "alias": req.get("alias"),
                    "property": req.get("property"),
                    "op": req.get("op", "eq"),
                    "value": value,
                }
            )
        if pattern.get("set_start"):
            out["start"] = dict(pattern["set_start"])
        for step in pattern.get("ensure_traverse") or []:
            _ensure_traverse(out, step)

    out["filter"] = filters

    defaults = rules.get("defaults") or {}
    if defaults.get("fill_as_name", True):
        for item in out.get("return") or []:
            if item.get("property") and not item.get("as_name"):
                alias = str(item.get("alias", "result"))
                prop = str(item["property"])
                item["as_name"] = f"{alias}_{prop}"

    if out.get("limit") is None and defaults.get("limit") is not None:
        out["limit"] = defaults["limit"]

    return out


def _resolve_mapping(
    *,
    mapping: dict[str, Any] | None,
    mapping_path: str | None,
) -> dict[str, Any]:
    if mapping is not None:
        return mapping
    if mapping_path is not None:
        return load_repair_mapping(mapping_path)
    return default_manufacturing_mapping()


def _compile(pattern: dict[str, Any]) -> re.Pattern[str]:
    flags = 0
    raw_flags = pattern.get("flags") or ""
    for name in str(raw_flags).replace("|", " ").split():
        flags |= _FLAG_MAP.get(name.upper(), 0)
    return re.compile(str(pattern["match"]), flags)


def _match_pattern(question: str, pattern: dict[str, Any]) -> re.Match[str] | None:
    if "match" not in pattern:
        return None
    return _compile(pattern).search(question)


def _filter_value(pattern: dict[str, Any], match: re.Match[str]) -> Any:
    if "literal_value" in pattern:
        return pattern["literal_value"]
    req = pattern.get("require_filter") or {}
    if "value" in req:
        return req["value"]
    capture = int(pattern.get("capture", 1))
    try:
        return match.group(capture)
    except IndexError:
        return match.group(0)


def _has_filter(filters: list[dict[str, Any]], req: dict[str, Any], value: Any) -> bool:
    prop = req.get("property")
    value_l = str(value).lower()
    for entry in filters:
        if str(entry.get("value", "")).lower() != value_l:
            continue
        if prop and str(entry.get("property")) != str(prop):
            continue
        return True
    return False


def _relationships(intent: dict[str, Any]) -> set[str]:
    return {str(step.get("relationship")) for step in intent.get("traverse") or []}


def _ensure_traverse(intent: dict[str, Any], step: dict[str, Any]) -> None:
    rel = step.get("relationship")
    if not rel or rel in _relationships(intent):
        return
    traverses: list[dict[str, Any]] = list(intent.get("traverse") or [])
    traverses.append(copy.deepcopy(step))
    intent["traverse"] = traverses
