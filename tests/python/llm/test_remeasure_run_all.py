"""Selection behavior of scripts/remeasure/run_all.sh (issue #142)."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "remeasure" / "run_all.sh"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def test_default_arms_are_offline_only():
    result = _run("--list-arms")
    assert result.returncode == 0, result.stderr
    arms = result.stdout.split()
    assert arms == ["track-a", "h1", "h2", "h3", "track-b", "dry-run", "field-match"]
    assert "h1-live" not in arms
    assert "track-b-exec" not in arms


def test_live_flag_adds_live_arms():
    result = _run("--live", "--list-arms")
    assert result.returncode == 0, result.stderr
    arms = result.stdout.split()
    assert "h1-live" in arms
    assert "track-b-exec" in arms


def test_only_accepts_aliases_and_deduplicates():
    result = _run("--only", "dry_run,h1_mechanical,h1", "--list-arms")
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["dry-run", "h1"]


def test_live_arm_requires_live_flag():
    result = _run("--only", "h1-live", "--list-arms")
    assert result.returncode == 2
    assert "--live" in result.stderr


def test_unknown_arm_is_rejected():
    result = _run("--only", "nope", "--list-arms")
    assert result.returncode == 2
    assert "unknown arm" in result.stderr
