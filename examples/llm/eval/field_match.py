"""Gold Intent field-match scorer (issue #96, step 1).

Deterministic, field-by-field comparison of a predicted Intent dict against a
gold Intent dict, aligned with the Intent schema in
``crates/ontographia-core/src/intent.rs``:

- ``entities``:    F1 over the class set (``start.class`` + ``traverse.to.class``)
- ``relations``:   F1 over resolved steps ``(from_class, relationship, direction, to_class)``
- ``filters``:     F1 over ``(owner_class, property, op, value)`` (alias resolved to class)
- ``projections``: F1 over ``(owner_class, property, aggregate)`` (``as_name`` ignored — cosmetic rename)
- ``limit``:       exact match (absent on both sides counts as a match)

Aliases are resolved to their owning class before comparison, so renaming an
alias consistently does not change the score. No LLM, no network.
"""

from __future__ import annotations

import json
from typing import Any

FIELDS = ("entities", "relations", "filters", "projections", "limit")


def _alias_class(intent: dict[str, Any]) -> dict[str, str]:
    """Map pattern alias -> owning class within one Intent."""
    out: dict[str, str] = {}
    start = intent.get("start") or {}
    if start.get("alias") and start.get("class"):
        out[str(start["alias"])] = str(start["class"])
    for step in intent.get("traverse", []) or []:
        to = step.get("to") or {}
        if to.get("alias") and to.get("class"):
            out[str(to["alias"])] = str(to["class"])
    return out


def _owner_class(intent: dict[str, Any], alias: Any) -> str:
    """Resolve an alias to its class; fall back to the raw alias string."""
    a = str(alias)
    return _alias_class(intent).get(a, a)


def _entity_set(intent: dict[str, Any]) -> set[str]:
    classes: set[str] = set()
    start = intent.get("start") or {}
    if start.get("class"):
        classes.add(str(start["class"]))
    for step in intent.get("traverse", []) or []:
        to = step.get("to") or {}
        if to.get("class"):
            classes.add(str(to["class"]))
    return classes


def _relation_set(intent: dict[str, Any]) -> set[tuple[str, str, str, str]]:
    """Resolved traverse steps: (from_class, relationship, direction, to_class)."""
    steps: set[tuple[str, str, str, str]] = set()
    start = intent.get("start") or {}
    prev_class = str(start.get("class") or "")
    for step in intent.get("traverse", []) or []:
        to = step.get("to") or {}
        to_class = str(to.get("class") or "")
        rel = str(step.get("relationship") or "")
        direction = str(step.get("direction") or "")
        steps.add((prev_class, rel, direction, to_class))
        prev_class = to_class
    return steps


def _canon_value(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _filter_set(intent: dict[str, Any]) -> set[tuple[str, str, str, str]]:
    out: set[tuple[str, str, str, str]] = set()
    for entry in intent.get("filter", []) or []:
        out.add(
            (
                _owner_class(intent, entry.get("alias")),
                str(entry.get("property") or ""),
                str(entry.get("op") or ""),
                _canon_value(entry.get("value")),
            )
        )
    return out


def _projection_set(intent: dict[str, Any]) -> set[tuple[str, str, str]]:
    out: set[tuple[str, str, str]] = set()
    for entry in intent.get("return", []) or []:
        out.add(
            (
                _owner_class(intent, entry.get("alias")),
                str(entry.get("property") or ""),
                str(entry.get("aggregate") or ""),
            )
        )
    return out


def _prf(pred: set[Any], gold: set[Any]) -> dict[str, float]:
    """Precision/recall/F1; both-empty scores 1.0 (vacuous match)."""
    if not pred and not gold:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    if not pred or not gold:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    tp = len(pred & gold)
    precision = tp / len(pred)
    recall = tp / len(gold)
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return {"precision": precision, "recall": recall, "f1": f1}


def _limit_match(pred: dict[str, Any], gold: dict[str, Any]) -> dict[str, float]:
    p = pred.get("limit")
    g = gold.get("limit")
    return {"match": 1.0 if p == g else 0.0}


def intent_field_match(pred: dict[str, Any], gold: dict[str, Any]) -> dict[str, Any]:
    """Score a predicted Intent against a gold Intent, field by field."""
    entities = _prf(_entity_set(pred), _entity_set(gold))
    relations = _prf(_relation_set(pred), _relation_set(gold))
    filters = _prf(_filter_set(pred), _filter_set(gold))
    projections = _prf(_projection_set(pred), _projection_set(gold))
    limit = _limit_match(pred, gold)

    field_f1 = {
        "entities": entities["f1"],
        "relations": relations["f1"],
        "filters": filters["f1"],
        "projections": projections["f1"],
        "limit": limit["match"],
    }
    return {
        "fields": {
            "entities": entities,
            "relations": relations,
            "filters": filters,
            "projections": projections,
            "limit": limit,
        },
        "field_f1": field_f1,
        "macro_f1": sum(field_f1.values()) / len(field_f1),
        "exact_match": all(v == 1.0 for v in field_f1.values()),
    }


def aggregate_scores(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-item ``intent_field_match`` results."""
    n = len(items)
    if n == 0:
        return {"n": 0, "exact_match_rate": 0.0, "macro_f1_mean": 0.0,
                "field_f1_mean": {f: 0.0 for f in FIELDS}}
    field_means = {
        f: sum(item["score"]["field_f1"][f] for item in items) / n for f in FIELDS
    }
    return {
        "n": n,
        "exact_match_rate": sum(1 for i in items if i["score"]["exact_match"]) / n,
        "macro_f1_mean": sum(i["score"]["macro_f1"] for i in items) / n,
        "field_f1_mean": field_means,
    }
