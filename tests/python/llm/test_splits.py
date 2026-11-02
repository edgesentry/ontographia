"""Frozen Track A splits and the predictions arm (issue #96, step 2)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from llm.eval import splits as splits_mod
from llm.eval.gold import build_gold_cases
from llm.eval.splits import (
    SEED,
    build_split,
    gold_fingerprint,
    load_split,
    partition_ids,
    split_path,
    verify_gold_hash,
)

ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / "examples" / "llm" / "eval" / "run_gold_field_match.py"


def test_split_regeneration_is_deterministic() -> None:
    a = build_split()
    b = build_split()
    assert a == b
    assert a["seed"] == SEED
    # The committed file is exactly what build_split() regenerates.
    committed = json.loads(split_path().read_text(encoding="utf-8"))
    assert a == committed


def test_split_strata_and_counts() -> None:
    split = load_split("track_a_v1")
    assert split["n_gold"] == 40
    assert len(split["strata"]) == 4
    for ids in split["strata"].values():
        assert len(ids) == 10

    test_ids = partition_ids(split, "test")
    assert len(test_ids) == 8
    # 2 held out per stratum.
    for name in split["strata"]:
        assert sum(1 for i in test_ids if i.startswith(name + "_")) == 2

    folds = split["partitions"]["folds"]
    assert len(folds) == 4
    for entry in folds:
        assert len(entry["ids"]) == 8
        # 2 per stratum per fold.
        for name in split["strata"]:
            assert sum(1 for i in entry["ids"] if i.startswith(name + "_")) == 2

    dev = partition_ids(split, "dev")
    assert len(dev) == 32
    assert set(dev) == set(partition_ids(split, "cv"))
    assert set(dev).isdisjoint(test_ids)
    assert sorted(set(dev) | set(test_ids)) == partition_ids(split, "all")


def test_fold_selector_bounds() -> None:
    split = load_split("track_a_v1")
    assert partition_ids(split, "fold:0") == split["partitions"]["folds"][0]["ids"]
    with pytest.raises(ValueError, match="no fold 4"):
        partition_ids(split, "fold:4")
    with pytest.raises(ValueError, match="unknown partition"):
        partition_ids(split, "bogus")


def test_gold_hash_matches_current_gold() -> None:
    split = load_split("track_a_v1")
    assert split["gold_hash"] == gold_fingerprint()


def test_gold_hash_mismatch_fails() -> None:
    split = load_split("track_a_v1")
    tampered = {**split, "gold_hash": "sha256:" + "0" * 64}
    with pytest.raises(ValueError, match="gold hash mismatch"):
        verify_gold_hash(tampered)


def _write_predictions_fixture(path: Path, partition: str) -> list[str]:
    split = load_split("track_a_v1")
    ids = partition_ids(split, partition)
    cases = {c.id: c for c in build_gold_cases()}
    with path.open("w", encoding="utf-8") as fh:
        for cid in sorted(ids):
            fh.write(json.dumps({"id": cid, "intent": cases[cid].intent}) + "\n")
    return sorted(ids)


def _run_runner(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def test_predictions_arm_json_shape(tmp_path: Path) -> None:
    fixture = tmp_path / "preds.jsonl"
    ids = _write_predictions_fixture(fixture, "test")
    result = _run_runner(
        "--arms", "predictions",
        "--predictions", str(fixture),
        "--split", "track_a_v1",
        "--partition", "test",
        "--model", "fixture-model",
        "--provider", "fixture-provider",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)

    # Required top-level keys (step 2 JSON score shape).
    assert payload["schema_version"] == "2.0"
    assert payload["git_rev"]
    assert payload["split"]["id"] == "track_a_v1"
    assert payload["split"]["version"]
    assert payload["split"]["gold_hash"].startswith("sha256:")
    assert payload["model"] == "fixture-model"
    assert payload["provider"] == "fixture-provider"

    assert len(payload["results"]) == 1
    arm = payload["results"][0]
    assert arm["arm"] == "predictions"
    assert arm["partition"] == "test"
    agg = arm["aggregate"]
    assert agg["n"] == len(ids) == 8
    # Fixture predicts the gold Intent verbatim: exact match everywhere.
    assert agg["exact_match_rate"] == 1.0
    assert agg["macro_f1_mean"] == 1.0
    assert arm["skipped"] == []
    assert "items" not in arm  # aggregate-only by default


def test_predictions_arm_cv_reports_per_fold(tmp_path: Path) -> None:
    fixture = tmp_path / "preds.jsonl"
    _write_predictions_fixture(fixture, "dev")
    result = _run_runner(
        "--arms", "predictions",
        "--predictions", str(fixture),
        "--split", "track_a_v1",
        "--partition", "cv",
    )
    assert result.returncode == 0, result.stderr
    arm = json.loads(result.stdout)["results"][0]
    assert arm["partition"] == "cv"
    assert arm["aggregate"]["n"] == 32
    assert [f["fold"] for f in arm["folds"]] == [0, 1, 2, 3]
    assert all(f["aggregate"]["n"] == 8 for f in arm["folds"])


def test_predictions_arm_requires_file() -> None:
    result = _run_runner("--arms", "predictions")
    assert result.returncode == 2
    assert "--predictions" in result.stderr


def test_predictions_arm_missing_ids_are_skipped(tmp_path: Path) -> None:
    fixture = tmp_path / "preds.jsonl"
    ids = _write_predictions_fixture(fixture, "test")
    # Drop one prediction; it must be reported as skipped, not crash.
    lines = fixture.read_text(encoding="utf-8").splitlines(keepends=True)
    fixture.write_text("".join(lines[1:]), encoding="utf-8")
    result = _run_runner(
        "--arms", "predictions",
        "--predictions", str(fixture),
        "--split", "track_a_v1",
        "--partition", "test",
    )
    assert result.returncode == 0, result.stderr
    arm = json.loads(result.stdout)["results"][0]
    assert arm["aggregate"]["n"] == 7
    assert arm["skipped"] == [ids[0]]


def test_split_gold_mismatch_fails_runner(tmp_path: Path, monkeypatch) -> None:
    """load_split must refuse a split whose frozen gold hash is stale."""
    bad = tmp_path / "bad_split.json"
    split = build_split("bad_split")
    split["gold_hash"] = "sha256:" + "f" * 64
    bad.write_text(json.dumps(split), encoding="utf-8")
    monkeypatch.setattr(splits_mod, "SPLIT_DIR", tmp_path)
    with pytest.raises(ValueError, match="gold hash mismatch"):
        load_split("bad_split")
