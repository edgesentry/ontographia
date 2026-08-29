"""Deterministic Intent JSON fixtures — stand in for LLM output in tests and offline demos."""

from __future__ import annotations

from typing import Any

MOCK_LLM_INTENTS: dict[str, dict[str, Any]] = {
    "List suppliers for parts in product SKU SPX-100": {
        "start": {"class": "Product", "alias": "product"},
        "traverse": [
            {
                "relationship": "has_part",
                "direction": "out",
                "to": {"class": "Part", "alias": "part"},
            },
            {
                "relationship": "supplied_by",
                "direction": "out",
                "to": {"class": "Supplier", "alias": "supplier"},
            },
        ],
        "filter": [
            {"alias": "product", "property": "sku", "op": "eq", "value": "SPX-100"}
        ],
        "return": [
            {"alias": "supplier", "property": "name", "as_name": "supplier_name"}
        ],
        "limit": 20,
    },
    "Which defect codes affect quarantined lots?": {
        "start": {"class": "Lot", "alias": "lot"},
        "traverse": [
            {
                "relationship": "has_defect",
                "direction": "out",
                "to": {"class": "DefectType", "alias": "defect"},
            }
        ],
        "filter": [
            {"alias": "lot", "property": "status", "op": "eq", "value": "quarantine"}
        ],
        "return": [
            {"alias": "defect", "property": "code", "as_name": "defect_code"}
        ],
        "limit": 20,
    },
    "Which plant hosts production Line-1?": {
        "start": {"class": "Line", "alias": "line"},
        "traverse": [
            {
                "relationship": "located_at",
                "direction": "out",
                "to": {"class": "Plant", "alias": "plant"},
            }
        ],
        "filter": [{"alias": "line", "property": "name", "op": "eq", "value": "Line-1"}],
        "return": [{"alias": "plant", "property": "name", "as_name": "plant_name"}],
        "limit": 20,
    },
}
