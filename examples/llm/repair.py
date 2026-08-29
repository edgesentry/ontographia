"""Deterministic repairs for common LLM Intent omissions."""

from __future__ import annotations

import copy
import re
from typing import Any


def repair_intent(question: str, intent: dict[str, Any]) -> dict[str, Any]:
    """Apply safe, question-driven fixes before semantic/engine validation."""
    out = copy.deepcopy(intent)
    filters: list[dict[str, Any]] = list(out.get("filter") or [])
    filter_values_lower = {str(f.get("value", "")).lower() for f in filters}
    question_lower = question.lower()

    sku_match = re.search(r"\bSKU\s+([A-Z0-9-]+)\b", question, re.IGNORECASE)
    if sku_match:
        sku = sku_match.group(1)
        if sku.lower() not in filter_values_lower:
            filters.append(
                {"alias": "product", "property": "sku", "op": "eq", "value": sku}
            )
        out["start"] = {"class": "Product", "alias": "product"}
        _ensure_bom_supplier_traverses(out)

    line_match = re.search(r"\b(Line-\d+)\b", question, re.IGNORECASE)
    if line_match:
        line_name = line_match.group(1)
        if line_name.lower() not in filter_values_lower:
            filters.append(
                {"alias": "line", "property": "name", "op": "eq", "value": line_name}
            )
        out["start"] = {"class": "Line", "alias": "line"}
        _ensure_line_plant_traverse(out)

    if "quarantine" in question_lower:
        if not any(
            str(f.get("property")) == "status"
            and str(f.get("value", "")).lower() == "quarantine"
            for f in filters
        ):
            filters.append(
                {
                    "alias": "lot",
                    "property": "status",
                    "op": "eq",
                    "value": "quarantine",
                }
            )
        out["start"] = {"class": "Lot", "alias": "lot"}
        _ensure_lot_defect_traverse(out)

    lot_match = re.search(r"\b(LOT-\d{4}-\d{3})\b", question, re.IGNORECASE)
    if lot_match:
        lot_id = lot_match.group(1)
        if lot_id.lower() not in filter_values_lower:
            filters.append(
                {"alias": "lot", "property": "lot_id", "op": "eq", "value": lot_id}
            )

    out["filter"] = filters

    for item in out.get("return") or []:
        if item.get("property") and not item.get("as_name"):
            alias = str(item.get("alias", "result"))
            prop = str(item["property"])
            item["as_name"] = f"{alias}_{prop}"

    if out.get("limit") is None:
        out["limit"] = 20

    return out


def _relationships(intent: dict[str, Any]) -> set[str]:
    return {str(step.get("relationship")) for step in intent.get("traverse") or []}


def _ensure_bom_supplier_traverses(intent: dict[str, Any]) -> None:
    traverses: list[dict[str, Any]] = list(intent.get("traverse") or [])
    rels = _relationships(intent)
    if "has_part" not in rels:
        traverses.append(
            {
                "relationship": "has_part",
                "direction": "out",
                "to": {"class": "Part", "alias": "part"},
            }
        )
    if "supplied_by" not in rels:
        traverses.append(
            {
                "relationship": "supplied_by",
                "direction": "out",
                "to": {"class": "Supplier", "alias": "supplier"},
            }
        )
    intent["traverse"] = traverses


def _ensure_line_plant_traverse(intent: dict[str, Any]) -> None:
    traverses: list[dict[str, Any]] = list(intent.get("traverse") or [])
    if "located_at" not in _relationships(intent):
        traverses.append(
            {
                "relationship": "located_at",
                "direction": "out",
                "to": {"class": "Plant", "alias": "plant"},
            }
        )
    intent["traverse"] = traverses


def _ensure_lot_defect_traverse(intent: dict[str, Any]) -> None:
    traverses: list[dict[str, Any]] = list(intent.get("traverse") or [])
    if "has_defect" not in _relationships(intent):
        traverses.append(
            {
                "relationship": "has_defect",
                "direction": "out",
                "to": {"class": "DefectType", "alias": "defect"},
            }
        )
    intent["traverse"] = traverses
