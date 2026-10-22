"""Ensure uv ``--group`` references in scripts/ and docs/ exist in pyproject.toml.

No network; parses local files only. Prevents mismatches like ``--group llm``
when the dependency group is named ``litellm`` (distinct from the
``ontographia[llm]`` package extra).
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Matches: --group NAME, --group=NAME (uv CLI forms).
_GROUP_REF = re.compile(
    r"--group(?:=|\s+)([A-Za-z0-9][A-Za-z0-9._-]*)",
)

# Directories to scan (issue #108).
_SCAN_DIRS = ("scripts", "docs")


def _defined_groups() -> set[str]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    groups = data.get("dependency-groups") or {}
    if not isinstance(groups, dict):
        pytest.fail("[dependency-groups] missing or invalid in pyproject.toml")
    return set(groups)


_TEXT_SUFFIXES = {
    ".sh",
    ".md",
    ".py",
    ".yml",
    ".yaml",
    ".toml",
    ".txt",
    ".example",
    ".json",
}


def _iter_text_files() -> list[Path]:
    files: list[Path] = []
    for name in _SCAN_DIRS:
        base = ROOT / name
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in _TEXT_SUFFIXES:
                files.append(path)
    return files


def test_uv_group_refs_exist_in_pyproject() -> None:
    defined = _defined_groups()
    assert defined, "expected at least one [dependency-groups] entry"

    missing: list[str] = []
    for path in _iter_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for match in _GROUP_REF.finditer(text):
            group = match.group(1)
            if group not in defined:
                rel = path.relative_to(ROOT)
                missing.append(f"{rel}: --group {group}")

    assert not missing, (
        "uv --group references not defined in pyproject.toml "
        f"[dependency-groups] ({sorted(defined)}):\n  "
        + "\n  ".join(missing)
    )


def test_litellm_group_excludes_malicious_release() -> None:
    """Lock/docs pin: litellm must exclude known-bad 1.107.0 (see pyproject.toml)."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    specs = (data.get("dependency-groups") or {}).get("litellm") or []
    joined = " ".join(specs)
    assert "litellm" in joined
    assert "!=1.107.0" in joined
