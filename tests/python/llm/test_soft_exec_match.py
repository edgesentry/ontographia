"""Offline unit tests for Track B Soft Exec Match (issue #73)."""

from __future__ import annotations

import json
from pathlib import Path

from llm.eval.run_track_b_exec import (
    format_summary_markdown,
    jaccard_rows,
    score_exec_pair,
    summarize_cases,
)
from llm.eval.soft_exec_match import (
    coerce_scalar,
    entity_jaccard,
    multiset_jaccard_and_f1,
    normalize_row,
    normalize_rows,
    score_soft_exec,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = ROOT / "examples" / "llm" / "eval" / "fixtures" / "soft_exec_cases.json"


def test_fixture_cases() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert len(cases) >= 5
    for case in cases:
        pred = case["pred_rows"]
        gold = case["gold_rows"]
        exp = case["expected"]

        exact_jac = round(jaccard_rows(pred, gold), 4)
        exact_match = exact_jac >= 1.0 - 1e-9
        assert exact_match is exp["exact_exec_match"], case["id"]
        assert exact_jac == exp["exact_jaccard"], case["id"]

        soft = score_soft_exec(pred, gold)
        assert soft["soft_exec_match"] is exp["soft_exec_match"], case["id"]
        assert soft["soft_jaccard"] == exp["soft_jaccard"], case["id"]
        assert soft["soft_f1"] == exp["soft_f1"], case["id"]
        if exp["has_entity_jaccard"]:
            assert "entity_jaccard" in soft, case["id"]
            assert soft["entity_jaccard"] == exp["entity_jaccard"], case["id"]
        else:
            assert "entity_jaccard" not in soft, case["id"]


def test_alias_mismatch_matches_soft_but_not_exact() -> None:
    pred = [{"movie_title": "The Matrix", "released": 1999}]
    gold = [{"m.title": "The Matrix", "m.released": 1999}]
    # Existing exact fingerprint includes column keys -> 0.0
    assert jaccard_rows(pred, gold) == 0.0
    # Soft strips column keys -> 1.0
    soft = score_soft_exec(pred, gold)
    assert soft["soft_exec_match"] is True
    assert soft["soft_jaccard"] == 1.0
    assert soft["soft_f1"] == 1.0
    assert "entity_jaccard" not in soft


def test_order_independence_rows_and_columns() -> None:
    pred = [
        {"b": 2, "a": "x"},
        {"b": 1, "a": "y"},
    ]
    gold = [
        {"col1": "y", "col2": 1.0},
        {"col1": "x", "col2": 2},
    ]
    assert normalize_rows(pred) == normalize_rows(gold)
    soft = score_soft_exec(pred, gold)
    assert soft["soft_exec_match"] is True
    assert soft["soft_jaccard"] == 1.0
    assert soft["soft_f1"] == 1.0


def test_multiset_duplicate_rows_sensitivity() -> None:
    pred = [{"name": "Alice"}, {"name": "Alice"}, {"name": "Bob"}]
    gold = [{"p.name": "Alice"}, {"p.name": "Bob"}]
    res = multiset_jaccard_and_f1(pred, gold)
    assert res["soft_exec_match"] is False
    # Intersection = 2 (one Alice, one Bob), Union = 3 (two Alices, one Bob)
    assert round(res["soft_jaccard"], 4) == round(2 / 3, 4)
    # Precision = 2/3, Recall = 2/2 = 1.0, F1 = 4/5 = 0.8
    assert round(res["soft_f1"], 4) == 0.8


def test_empty_vs_empty_and_one_sided_empty() -> None:
    both_empty = score_soft_exec([], [])
    assert both_empty["soft_exec_match"] is True
    assert both_empty["soft_jaccard"] == 1.0
    assert both_empty["soft_f1"] == 1.0
    assert "entity_jaccard" not in both_empty

    one_empty = score_soft_exec([], [{"a": 1}])
    assert one_empty["soft_exec_match"] is False
    assert one_empty["soft_jaccard"] == 0.0
    assert one_empty["soft_f1"] == 0.0


def test_null_handling_distinct_from_falsy_scalars() -> None:
    assert coerce_scalar(None) == ("null", "")
    assert coerce_scalar(None) != coerce_scalar("")
    assert coerce_scalar(None) != coerce_scalar(0)
    assert coerce_scalar(None) != coerce_scalar(False)
    assert coerce_scalar(False) != coerce_scalar(0)
    assert coerce_scalar(True) != coerce_scalar(1)
    assert coerce_scalar(1) == coerce_scalar(1.0)

    # Mixed types with None in rows must sort deterministically without TypeError
    r1 = normalize_row({"a": None, "b": 1, "c": "text", "d": False})
    r2 = normalize_row({"x": False, "y": "text", "z": 1.0, "w": None})
    assert r1 == r2

    # Null vs empty string does not match
    soft_mismatch = score_soft_exec([{"x": None}], [{"x": ""}])
    assert soft_mismatch["soft_exec_match"] is False
    assert soft_mismatch["soft_jaccard"] == 0.0


def test_non_overlap_scores_zero() -> None:
    pred = [{"name": "Plant-A", "count": 10}]
    gold = [{"name": "Plant-B", "count": 20}]
    soft = score_soft_exec(pred, gold)
    assert soft["soft_exec_match"] is False
    assert soft["soft_jaccard"] == 0.0
    assert soft["soft_f1"] == 0.0


def test_entity_jaccard_optional_only_when_ids_present() -> None:
    # No IDs -> None (never forced)
    no_ids_pred = [{"title": "The Matrix"}]
    no_ids_gold = [{"m.title": "The Matrix"}]
    assert entity_jaccard(no_ids_pred, no_ids_gold) is None
    assert "entity_jaccard" not in score_soft_exec(no_ids_pred, no_ids_gold)

    # IDs present on both sides -> computed
    id_pred = [{"movieId": "m1", "title": "The Matrix"}, {"movieId": "m2", "title": "Speed"}]
    id_gold = [{"m.id": "m1"}, {"m.id": "m3"}]
    assert round(entity_jaccard(id_pred, id_gold) or 0.0, 4) == 0.3333
    scored = score_soft_exec(id_pred, id_gold)
    assert scored["entity_jaccard"] == 0.3333


def test_run_track_b_exec_wiring_and_rollups() -> None:
    # Case 1: exact mismatch due to alias, but soft match = True
    c1 = score_exec_pair(
        {
            "i": 0,
            "ref": "neo4jlabs_demo_db_movies",
            "compile_ok": True,
            "structure": {"label_f1": 1.0, "rel_f1": 1.0, "prop_f1": 1.0},
        },
        [{"movie_title": "The Matrix"}],
        [{"m.title": "The Matrix"}],
    )
    assert c1["exec_match"] is False
    assert c1["jaccard"] == 0.0
    assert c1["soft_exec_match"] is True
    assert c1["soft_jaccard"] == 1.0
    assert c1["soft_f1"] == 1.0
    assert c1["note"] == "exec_mismatch"

    # Case 2: compile_failed -> excluded from exec_scored and soft rollups
    c2 = {
        "i": 1,
        "ref": "neo4jlabs_demo_db_movies",
        "compile_ok": False,
        "exec_match": None,
        "jaccard": None,
        "soft_exec_match": None,
        "soft_jaccard": None,
        "soft_f1": None,
        "note": "compile_failed",
        "structure": {"label_f1": 0.0, "rel_f1": 0.0, "prop_f1": 0.0},
    }

    # Case 3: exact and soft match with entity IDs
    c3 = score_exec_pair(
        {
            "i": 2,
            "ref": "neo4jlabs_demo_db_recommendations",
            "compile_ok": True,
            "structure": {"label_f1": 0.5, "rel_f1": 0.5, "prop_f1": 0.5},
        },
        [{"id": 42, "title": "Heat"}],
        [{"id": 42, "title": "Heat"}],
    )
    assert c3["exec_match"] is True
    assert c3["soft_exec_match"] is True
    assert c3["entity_jaccard"] == 1.0

    summary = summarize_cases([c1, c2, c3])
    assert summary["n"] == 3
    assert summary["compile_ok"] == 2
    assert summary["exec_scored"] == 2
    assert summary["exec_match"] == 1
    assert summary["exec_match_rate"] == 0.5
    assert summary["jaccard_mean"] == 0.5
    assert summary["soft_exec_match"] == 2
    assert summary["soft_exec_match_rate"] == 1.0
    assert summary["soft_jaccard_mean"] == 1.0
    assert summary["soft_f1_mean"] == 1.0
    assert summary["entity_jaccard_scored"] == 1
    assert summary["entity_jaccard_mean"] == 1.0
    assert summary["by_ref"]["neo4jlabs_demo_db_movies"]["soft_exec_match_rate"] == 1.0

    md = format_summary_markdown(
        {
            "meta": {
                "recorded_at": "2026-11-03T00:00:00Z",
                "git_rev": "deadbee",
                "model": "test-model",
                "refs": ["neo4jlabs_demo_db_movies", "neo4jlabs_demo_db_recommendations"],
                "n": 3,
                "seed": 53,
                "neo4j_uri": "neo4j+s://demo.neo4jlabs.com",
            },
            "results": {"summary": summary},
        }
    )
    assert "Soft Exec Match: 2 / 2 (rate=1.0)" in md
    assert "Soft Jaccard mean: 1.0" in md
    assert "Soft F1 mean: 1.0" in md
