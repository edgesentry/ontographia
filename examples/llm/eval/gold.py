"""Track A gold questions/Intents and plausible silent-wrong variants."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from .distractor import near_duplicate_map

# Alias -> class for manufacturing gold intents
ALIAS_CLASS = {
    "product": "Product",
    "part": "Part",
    "supplier": "Supplier",
    "plant": "Plant",
    "line": "Line",
    "lot": "Lot",
    "defect": "DefectType",
}


@dataclass(frozen=True)
class GoldCase:
    id: str
    question: str
    intent: dict[str, Any]
    # For silent-wrong: which return/filter slot to corrupt (alias, property)
    corrupt_target: tuple[str, str] | None = None


def _bom(sku: str) -> dict[str, Any]:
    return {
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
            {"alias": "product", "property": "sku", "op": "eq", "value": sku}
        ],
        "return": [
            {"alias": "supplier", "property": "name", "as_name": "supplier_name"}
        ],
        "limit": 20,
    }


def _plant_for_line(line: str) -> dict[str, Any]:
    return {
        "start": {"class": "Line", "alias": "line"},
        "traverse": [
            {
                "relationship": "located_at",
                "direction": "out",
                "to": {"class": "Plant", "alias": "plant"},
            }
        ],
        "filter": [{"alias": "line", "property": "name", "op": "eq", "value": line}],
        "return": [{"alias": "plant", "property": "name", "as_name": "plant_name"}],
        "limit": 20,
    }


def _defects_for_status(status: str) -> dict[str, Any]:
    return {
        "start": {"class": "Lot", "alias": "lot"},
        "traverse": [
            {
                "relationship": "has_defect",
                "direction": "out",
                "to": {"class": "DefectType", "alias": "defect"},
            }
        ],
        "filter": [
            {"alias": "lot", "property": "status", "op": "eq", "value": status}
        ],
        "return": [
            {"alias": "defect", "property": "code", "as_name": "defect_code"}
        ],
        "limit": 20,
    }


def _lot_on_line(lot_id: str) -> dict[str, Any]:
    return {
        "start": {"class": "Lot", "alias": "lot"},
        "traverse": [
            {
                "relationship": "produced_on",
                "direction": "out",
                "to": {"class": "Line", "alias": "line"},
            }
        ],
        "filter": [{"alias": "lot", "property": "lot_id", "op": "eq", "value": lot_id}],
        "return": [{"alias": "line", "property": "name", "as_name": "line_name"}],
        "limit": 20,
    }


def build_gold_cases() -> list[GoldCase]:
    cases: list[GoldCase] = []

    skus = [f"SPX-{n}" for n in (100, 200, 300, 400, 500, 600, 700, 800, 900, 1000)]
    for i, sku in enumerate(skus):
        cases.append(
            GoldCase(
                id=f"bom_suppliers_{i:02d}",
                question=f"List suppliers for parts in product SKU {sku}",
                intent=_bom(sku),
                corrupt_target=("supplier", "name"),
            )
        )

    lines = [f"Line-{n}" for n in range(1, 11)]
    for i, line in enumerate(lines):
        cases.append(
            GoldCase(
                id=f"line_plant_{i:02d}",
                question=f"Which plant hosts production {line}?",
                intent=_plant_for_line(line),
                corrupt_target=("plant", "name"),
            )
        )

    statuses = [
        "quarantine",
        "released",
        "hold",
        "scrap",
        "in_process",
        "approved",
        "rejected",
        "rework",
        "shipped",
        "open",
    ]
    for i, status in enumerate(statuses):
        cases.append(
            GoldCase(
                id=f"lot_defect_{i:02d}",
                question=f"Which defect codes affect lots with status {status}?",
                intent=_defects_for_status(status),
                corrupt_target=("defect", "code"),
            )
        )

    lots = [f"LOT-{n:04d}" for n in range(1, 11)]
    for i, lot_id in enumerate(lots):
        cases.append(
            GoldCase(
                id=f"lot_line_{i:02d}",
                question=f"Which production line produced lot {lot_id}?",
                intent=_lot_on_line(lot_id),
                corrupt_target=("line", "name"),
            )
        )

    assert len(cases) >= 30, len(cases)
    return cases


def make_silent_wrong_intent(intent: dict[str, Any], corrupt_target: tuple[str, str]) -> dict[str, Any] | None:
    """Swap a gold property for a near-duplicate distractor on the same class.

    The result still uses vocabulary present on mid/large ontologies, so
    Engine::build succeeds — the failure mode Kervin described.
    """
    alias, gold_prop = corrupt_target
    owner = ALIAS_CLASS.get(alias)
    if not owner:
        return None
    distractor = near_duplicate_map().get((owner, gold_prop))
    if not distractor:
        return None

    wrong = copy.deepcopy(intent)
    for entry in wrong.get("return", []):
        if entry.get("alias") == alias and entry.get("property") == gold_prop:
            entry["property"] = distractor
            return wrong
    for entry in wrong.get("filter", []):
        if entry.get("alias") == alias and entry.get("property") == gold_prop:
            entry["property"] = distractor
            return wrong
    return None
