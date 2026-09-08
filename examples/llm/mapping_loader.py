"""Load Intent repair / semantic-validate mapping YAML (issue #48)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

MAPPINGS_DIR = Path(__file__).resolve().parent / "mappings"
DEFAULT_MAPPING_PATH = MAPPINGS_DIR / "manufacturing.repair.yaml"


def load_repair_mapping(path: str | Path | None = None) -> dict[str, Any]:
    """Load a repair mapping YAML. ``None`` → manufacturing default."""
    resolved = Path(path) if path is not None else DEFAULT_MAPPING_PATH
    if not resolved.is_file():
        raise FileNotFoundError(f"repair mapping not found: {resolved}")
    data = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"repair mapping must be a mapping document: {resolved}")
    data.setdefault("defaults", {})
    data.setdefault("entity_patterns", [])
    data["_path"] = str(resolved)
    return data


@lru_cache(maxsize=8)
def default_manufacturing_mapping() -> dict[str, Any]:
    return load_repair_mapping(DEFAULT_MAPPING_PATH)
