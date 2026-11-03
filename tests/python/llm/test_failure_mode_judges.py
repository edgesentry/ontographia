"""Failure-mode judges and dry-run wiring (issue #96, step 3a)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from llm.eval.gold import build_gold_cases
from llm.eval.judges import (
    MODES,
    VARIANTS,
    FixtureResponder,
    build_judge_messages,
    build_variants,
    derive_mode_labels,
    fixture_path,
    load_fixture_answers,
    parse_judge_response,
    run_judge,
    score_judge_items,
)

ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / "examples" / "llm" / "eval" / "run_failure_mode_judges.py"

ONTOLOGY = {
    "classes": [{"name": "Line"}, {"name": "Plant"}],
    "relationships": [
        {
            "name": "located_at",
            "from_class": "Line",
            "to_class": "Plant",
            "direction": "out",
        }
    ],
    "properties": [
        {"name": "name", "owner_class": "Line"},
        {"name": "name", "owner_class": "Plant"},
    ],
}

GOLD_INTENT = {
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

QUESTION = "Which plant hosts production Line-1?"


# --- prompt build -----------------------------------------------------------


@pytest.mark.parametrize("mode", MODES)
def test_prompt_contains_required_blocks(mode: str) -> None:
    messages = build_judge_messages(mode, QUESTION, GOLD_INTENT, ONTOLOGY)
    assert [m["role"] for m in messages] == ["system", "user"]
    system, user = messages[0]["content"], messages[1]["content"]

    assert mode in system
    assert '"answer"' in system
    assert "yes" in system and "no" in system and "unknown" in system
    assert "QUESTION" in user and QUESTION in user
    assert "INTENT" in user
    assert "ONTOLOGY SUBSET" in user
    assert "located_at" in user and "Line -> Plant" in user
    assert "Plant: name" in user


def test_prompts_differ_per_mode() -> None:
    prompts = {
        mode: build_judge_messages(mode, QUESTION, GOLD_INTENT, ONTOLOGY)[0]["content"]
        for mode in MODES
    }
    assert len(set(prompts.values())) == len(MODES)


def test_unknown_mode_raises() -> None:
    with pytest.raises(ValueError, match="unknown judge mode"):
        build_judge_messages("made_up", QUESTION, GOLD_INTENT, ONTOLOGY)


# --- response parse ---------------------------------------------------------


def test_parse_accepts_object_fenced_json_and_case() -> None:
    assert parse_judge_response("missing_filter", {"answer": "YES"}) == {
        "mode": "missing_filter",
        "answer": "yes",
    }
    fenced = parse_judge_response(
        "wrong_relation", '```json\n{"answer": "no", "rationale": "ok"}\n```'
    )
    assert fenced == {
        "mode": "wrong_relation",
        "answer": "no",
        "rationale": "ok",
    }


@pytest.mark.parametrize(
    "raw",
    [
        "{not json",
        '{"answer": "maybe"}',
        '{"rationale": "no answer"}',
        "[]",
        None,
    ],
)
def test_bad_json_or_answer_is_unknown(raw) -> None:
    result = parse_judge_response("over_broad_scope", raw)
    assert result["mode"] == "over_broad_scope"
    assert result["answer"] == "unknown"
    assert "rationale" in result


def test_run_judge_uses_responder_and_parse() -> None:
    seen: list[str] = []

    def responder(mode: str, messages: list[dict[str, str]]) -> str:
        assert mode == "wrong_relation"
        assert messages[1]["content"].startswith("QUESTION:")
        seen.append(mode)
        return '{"answer": "yes", "rationale": "bad edge"}'

    result = run_judge(
        "wrong_relation", QUESTION, GOLD_INTENT, ONTOLOGY, responder
    )
    assert result == {
        "mode": "wrong_relation",
        "answer": "yes",
        "rationale": "bad edge",
    }
    assert seen == ["wrong_relation"]


# --- fixtures ---------------------------------------------------------------


def test_fixtures_cover_yes_and_no_per_mode() -> None:
    answers = load_fixture_answers()
    for mode in MODES:
        observed = {
            str(response["answer"])
            for (variant, m), response in answers.items()
            if m == mode
        }
        assert "yes" in observed, f"no positive fixture for {mode}"
        assert "no" in observed, f"no negative fixture for {mode}"


@pytest.mark.parametrize("variant", VARIANTS)
def test_fixture_responses_answer_each_mode(variant: str) -> None:
    answers = load_fixture_answers()
    responder = FixtureResponder(answers).for_variant(variant)
    for mode in MODES:
        result = run_judge(mode, QUESTION, GOLD_INTENT, ONTOLOGY, responder)
        assert result["mode"] == mode
        assert result["answer"] == answers[(variant, mode)]["answer"]


def test_fixtures_match_derived_labels(manufacturing_ontology) -> None:
    """Fixture answers must stay aligned with the field-match label rules."""
    answers = load_fixture_answers()
    cases = {c.id: c for c in build_gold_cases()}
    for case_id in ("line_plant_00", "bom_suppliers_00", "lot_defect_00"):
        case = cases[case_id]
        variants = dict(build_variants(case, manufacturing_ontology))
        assert set(variants) == set(VARIANTS)
        for variant, intent in variants.items():
            labels = derive_mode_labels(case.intent, intent)
            for mode in MODES:
                assert answers[(variant, mode)]["answer"] == (
                    "yes" if labels[mode] else "no"
                ), f"{case_id} {variant} {mode}"


def test_wrong_filter_value_is_not_missing_filter() -> None:
    """A same-slot filter with a different value is a wrong value, not a gap."""
    case = {c.id: c for c in build_gold_cases()}["line_plant_00"]
    wrong_value = json.loads(json.dumps(case.intent))
    wrong_value["filter"][0]["value"] = "Line-99"
    labels = derive_mode_labels(case.intent, wrong_value)
    assert labels == {m: False for m in MODES}


def test_variants_label_one_mode_each(manufacturing_ontology) -> None:
    case = {c.id: c for c in build_gold_cases()}["line_plant_00"]
    variants = dict(build_variants(case, manufacturing_ontology))

    def labels(name: str) -> dict[str, bool]:
        return derive_mode_labels(case.intent, variants[name])

    assert labels("gold") == {m: False for m in MODES}
    assert labels("silent_wrong") == {m: False for m in MODES}
    assert labels("swap_relation") == {
        "wrong_relation": True,
        "missing_filter": False,
        "over_broad_scope": False,
    }
    assert labels("drop_filter") == {
        "wrong_relation": False,
        "missing_filter": True,
        "over_broad_scope": False,
    }
    assert labels("drop_traverse") == {
        "wrong_relation": False,
        "missing_filter": False,
        "over_broad_scope": True,
    }


def test_fixture_path_exists() -> None:
    assert fixture_path().is_file()


# --- scoring ----------------------------------------------------------------


def test_score_judge_items_counts_and_abstention() -> None:
    items = [
        {"mode": "wrong_relation", "expected": "yes", "answer": "yes"},
        {"mode": "wrong_relation", "expected": "yes", "answer": "no"},
        {"mode": "wrong_relation", "expected": "no", "answer": "yes"},
        {"mode": "wrong_relation", "expected": "no", "answer": "no"},
        {"mode": "wrong_relation", "expected": "no", "answer": "unknown"},
        {"mode": "missing_filter", "expected": "yes", "answer": "yes"},
    ]
    scores = score_judge_items(items)

    wrong = scores["wrong_relation"]
    assert (wrong["tp"], wrong["fp"], wrong["fn"], wrong["tn"]) == (1, 1, 1, 1)
    assert wrong["n"] == 5
    assert wrong["n_answered"] == 4
    assert wrong["n_unknown"] == 1
    assert wrong["precision"] == 0.5
    assert wrong["recall"] == 0.5
    assert wrong["f1"] == 0.5

    missing = scores["missing_filter"]
    assert (missing["tp"], missing["fp"], missing["fn"], missing["tn"]) == (1, 0, 0, 0)
    assert missing["precision"] == 1.0 and missing["recall"] == 1.0
    # No items for this mode -> undefined metrics, not a crash or a fake 0.0.
    assert scores["over_broad_scope"]["n"] == 0
    assert scores["over_broad_scope"]["precision"] is None
    assert scores["over_broad_scope"]["recall"] is None
    assert scores["over_broad_scope"]["f1"] is None

    # All-negative slice with a correct judge: specificity is tn, not precision 0.
    negative_only = score_judge_items(
        [{"mode": "over_broad_scope", "expected": "no", "answer": "no"}]
    )["over_broad_scope"]
    assert negative_only["tn"] == 1
    assert negative_only["precision"] is None
    assert negative_only["recall"] is None


# --- CLI / split wiring -----------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def test_dry_run_cli_on_split_partition(tmp_path: Path) -> None:
    out = tmp_path / "judges.json"
    result = _run_cli(
        "--dry-run",
        "--split", "track_a_v1",
        "--partition", "test",
        "--json-out", str(out),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)

    assert payload["schema_version"] == "1.0"
    assert payload["git_rev"]
    assert payload["selection"] == "dry_run_fixture"
    assert payload["split"]["id"] == "track_a_v1"
    assert payload["split"]["version"]
    assert payload["split"]["gold_hash"].startswith("sha256:")
    assert payload["partition"] == "test"
    assert payload["n_cases"] == 8
    assert set(payload["judges"]) == set(MODES)
    assert set(payload["by_variant"]) == set(VARIANTS)
    for mode in MODES:
        assert payload["judges"][mode]["precision"] == 1.0
        assert payload["judges"][mode]["recall"] == 1.0
        assert payload["judges"][mode]["n_unknown"] == 0
    assert "items" not in payload
    assert json.loads(out.read_text(encoding="utf-8"))["partition"] == "test"


def test_dry_run_cli_predictions_arm(tmp_path: Path) -> None:
    cases = {c.id: c for c in build_gold_cases()}
    preds = tmp_path / "preds.jsonl"
    with preds.open("w", encoding="utf-8") as fh:
        for case_id in [
            "bom_suppliers_00",
            "line_plant_01",
            "lot_defect_03",
            "lot_line_03",
        ]:
            fh.write(json.dumps({"id": case_id, "intent": cases[case_id].intent}) + "\n")

    result = _run_cli(
        "--dry-run",
        "--predictions", str(preds),
        "--split", "track_a_v1",
        "--partition", "fold:0",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["partition"] == "fold:0"
    assert payload["n_cases"] == 8
    # 8 cases x 5 synthetic variants x 3 modes + 4 predictions x 3 modes.
    assert payload["n_items"] == 8 * 5 * 3 + 4 * 3
    predictions = payload["by_variant"]["predictions"]
    assert predictions["wrong_relation"]["n"] == 4
    assert predictions["wrong_relation"]["n_unknown"] == 4
    assert payload["skipped"] == [
        "bom_suppliers_06",
        "line_plant_09",
        "lot_defect_05",
        "lot_line_06",
    ]


def test_cli_requires_explicit_mode() -> None:
    result = _run_cli("--split", "track_a_v1", "--partition", "test")
    assert result.returncode == 2
    assert "--dry-run" in result.stderr and "--live" in result.stderr


def test_cli_rejects_both_modes() -> None:
    result = _run_cli("--dry-run", "--live")
    assert result.returncode == 2
    assert "mutually exclusive" in result.stderr


def test_cli_rejects_partition_without_split() -> None:
    result = _run_cli("--dry-run", "--partition", "test")
    assert result.returncode == 2
    assert "--partition requires --split" in result.stderr


def test_cli_rejects_unknown_partition() -> None:
    result = _run_cli("--dry-run", "--split", "track_a_v1", "--partition", "nope")
    assert result.returncode == 2
    assert "split error" in result.stderr
