"""Unit tests for scripts/remeasure/aggregate_h1_live.py (issue #142)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "remeasure" / "aggregate_h1_live.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("aggregate_h1_live", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payload(profile: str, hit: float, compile_ok: int, p95: int) -> dict:
    return {
        "meta": {
            "recorded_at": "2026-01-01T00:00:00Z",
            "git_rev": "abc1234",
            "model": "test-alias",
            "base_url": "http://127.0.0.1:4000/v1",
            "profiles": [profile],
            "n_cases": 40,
        },
        "verdict": {"verdict": "support"},
        "results": [
            {
                "profile": profile,
                "conditions": {
                    "full": {
                        "n": 40,
                        "property_hit_mean": hit,
                        "compile_ok": compile_ok,
                        "fallback_rate": 0.0,
                        "mean_llm_calls": 1.0,
                        "prompt_approx_tokens_p95": p95,
                        "near_dup_picked": 0,
                        "invent_without_seeing": 0,
                    }
                },
            }
        ],
    }


def test_natural_sort_orders_run10_after_run9():
    module = _load_module()
    names = [Path("run10.json"), Path("run2.json"), Path("run1.json")]
    assert [p.name for p in sorted(names, key=module.natural_key)] == [
        "run1.json",
        "run2.json",
        "run10.json",
    ]


def test_aggregate_means_and_ranges(tmp_path: Path):
    module = _load_module()
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    (json_dir / "run1.json").write_text(json.dumps(_payload("large", 0.80, 32, 1000)))
    (json_dir / "run2.json").write_text(json.dumps(_payload("large", 0.90, 36, 2000)))

    runs = [(p, module.load_run(p)) for p in sorted(json_dir.glob("run*.json"))]
    metrics = module.summarize(runs)["large"]["full"]

    assert metrics["runs"] == 2
    assert metrics["n_total"] == 80
    assert metrics["property_hit_mean"] == pytest.approx(0.85)
    assert metrics["property_hit_min"] == pytest.approx(0.80)
    assert metrics["property_hit_max"] == pytest.approx(0.90)
    assert metrics["compile_ok"] == 68
    assert metrics["compile_ok_rate"] == pytest.approx(0.85)
    assert metrics["prompt_tokens_p95_mean"] == pytest.approx(1500.0)
    assert "subset" not in module.summarize(runs)["large"]


def test_cli_writes_aggregate_and_index(tmp_path: Path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    (json_dir / "run1.json").write_text(json.dumps(_payload("mid", 0.75, 30, 1200)))

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--out-dir", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    aggregate = json.loads((tmp_path / "aggregate.json").read_text())
    index = json.loads((tmp_path / "aggregate_index.json").read_text())
    assert aggregate["runs"] == 1
    assert aggregate["metrics"]["mid"]["full"]["property_hit_mean"] == pytest.approx(0.75)
    assert index["files"] == ["run1.json"]
    assert index["per_run"][0]["verdict"] == "support"
    assert (tmp_path / "aggregate.md").read_text().startswith("# H1 live remeasure aggregate")


def test_cli_fails_without_runs(tmp_path: Path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--out-dir", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "no run*.json" in result.stderr
