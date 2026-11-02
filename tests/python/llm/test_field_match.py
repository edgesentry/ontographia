"""Unit checks for the gold Intent field-match scorer (issue #96, step 1)."""

from __future__ import annotations

import copy

from llm.eval.field_match import aggregate_scores, intent_field_match
from llm.eval.gold import build_gold_cases, make_silent_wrong_intent

GOLD = {
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
}


def test_exact_match_scores_perfect() -> None:
    score = intent_field_match(copy.deepcopy(GOLD), GOLD)
    assert score["exact_match"] is True
    assert score["macro_f1"] == 1.0
    assert all(v == 1.0 for v in score["field_f1"].values())


def test_alias_rename_is_cosmetic() -> None:
    """Renaming aliases consistently must not change the score."""
    pred = copy.deepcopy(GOLD)
    pred["start"]["alias"] = "l"
    pred["traverse"][0]["to"]["alias"] = "p"
    pred["filter"][0]["alias"] = "l"
    pred["return"][0]["alias"] = "p"
    pred["return"][0]["as_name"] = "where"
    score = intent_field_match(pred, GOLD)
    assert score["exact_match"] is True


def test_near_miss_wrong_property() -> None:
    """Distractor property on the projection: projections drop, rest stays 1.0."""
    pred = copy.deepcopy(GOLD)
    pred["return"][0]["property"] = "PlantName"  # near-duplicate distractor
    score = intent_field_match(pred, GOLD)
    assert score["exact_match"] is False
    assert score["field_f1"]["projections"] == 0.0
    assert score["field_f1"]["entities"] == 1.0
    assert score["field_f1"]["relations"] == 1.0
    assert score["field_f1"]["filters"] == 1.0
    assert score["field_f1"]["limit"] == 1.0


def test_missing_filter() -> None:
    pred = copy.deepcopy(GOLD)
    pred["filter"] = []
    score = intent_field_match(pred, GOLD)
    assert score["exact_match"] is False
    assert score["field_f1"]["filters"] == 0.0
    assert score["fields"]["filters"]["precision"] == 0.0
    assert score["fields"]["filters"]["recall"] == 0.0


def test_extra_filter_hurts_precision_not_recall() -> None:
    pred = copy.deepcopy(GOLD)
    pred["filter"] = pred["filter"] + [
        {"alias": "plant", "property": "name", "op": "eq", "value": "Plant-A"}
    ]
    score = intent_field_match(pred, GOLD)
    assert score["fields"]["filters"]["recall"] == 1.0
    assert score["fields"]["filters"]["precision"] == 0.5


def test_empty_projection() -> None:
    # Both empty -> vacuous match.
    both_empty_pred = {**copy.deepcopy(GOLD), "return": []}
    both_empty_gold = {**copy.deepcopy(GOLD), "return": []}
    score = intent_field_match(both_empty_pred, both_empty_gold)
    assert score["field_f1"]["projections"] == 1.0
    # Pred empty, gold non-empty -> 0.0.
    score = intent_field_match(both_empty_pred, GOLD)
    assert score["field_f1"]["projections"] == 0.0
    assert score["exact_match"] is False


def test_limit_mismatch_and_absent() -> None:
    pred = copy.deepcopy(GOLD)
    pred["limit"] = 50
    assert intent_field_match(pred, GOLD)["field_f1"]["limit"] == 0.0
    pred.pop("limit")
    gold_no_limit = copy.deepcopy(GOLD)
    gold_no_limit.pop("limit")
    assert intent_field_match(pred, gold_no_limit)["field_f1"]["limit"] == 1.0


def test_track_a_gold_self_scores_perfect() -> None:
    cases = build_gold_cases()
    assert len(cases) == 40
    items = [
        {"id": c.id, "score": intent_field_match(copy.deepcopy(c.intent), c.intent)}
        for c in cases
    ]
    agg = aggregate_scores(items)
    assert agg["exact_match_rate"] == 1.0
    assert agg["macro_f1_mean"] == 1.0


def test_track_a_silent_wrong_degrades_exactly_one_field() -> None:
    cases = build_gold_cases()
    items = []
    for c in cases:
        wrong = make_silent_wrong_intent(c.intent, c.corrupt_target)
        assert wrong is not None, c.id
        items.append({"id": c.id, "score": intent_field_match(wrong, c.intent)})
    agg = aggregate_scores(items)
    assert agg["exact_match_rate"] == 0.0
    # The corruption swaps one property in return or filter; entities/relations/limit untouched.
    assert agg["field_f1_mean"]["entities"] == 1.0
    assert agg["field_f1_mean"]["relations"] == 1.0
    assert agg["field_f1_mean"]["limit"] == 1.0
    assert agg["field_f1_mean"]["projections"] < 1.0
    assert agg["macro_f1_mean"] < 1.0
