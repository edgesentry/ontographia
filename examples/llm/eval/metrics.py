"""Track A metrics helpers."""

from __future__ import annotations

from typing import Any


def approx_tokens(text: str) -> int:
    """Cheap token proxy (chars/4). Good enough for relative comparisons."""
    return max(1, (len(text) + 3) // 4)


def _prop_set(intent: dict[str, Any]) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for key in ("filter", "return"):
        for entry in intent.get(key, []) or []:
            alias = entry.get("alias")
            prop = entry.get("property")
            if alias and prop:
                out.add((str(alias), str(prop)))
    return out


def _rel_set(intent: dict[str, Any]) -> set[str]:
    return {
        str(step["relationship"])
        for step in intent.get("traverse", []) or []
        if step.get("relationship")
    }


def _class_set(intent: dict[str, Any]) -> set[str]:
    classes: set[str] = set()
    start = intent.get("start") or {}
    if start.get("class"):
        classes.add(str(start["class"]))
    for step in intent.get("traverse", []) or []:
        to = step.get("to") or {}
        if to.get("class"):
            classes.add(str(to["class"]))
    return classes


def _f1(pred: set[Any], gold: set[Any]) -> float:
    if not pred and not gold:
        return 1.0
    if not pred or not gold:
        return 0.0
    tp = len(pred & gold)
    precision = tp / len(pred)
    recall = tp / len(gold)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def intent_soft_f1(pred: dict[str, Any], gold: dict[str, Any]) -> dict[str, float]:
    return {
        "class_f1": _f1(_class_set(pred), _class_set(gold)),
        "rel_f1": _f1(_rel_set(pred), _rel_set(gold)),
        "prop_f1": _f1(_prop_set(pred), _prop_set(gold)),
    }


def property_hit(pred: dict[str, Any], gold: dict[str, Any]) -> float:
    """Fraction of gold (alias, property) pairs present in pred."""
    g = _prop_set(gold)
    if not g:
        return 1.0
    p = _prop_set(pred)
    return len(g & p) / len(g)
