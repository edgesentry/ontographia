"""Shared fixtures for ontographia.llm tests (no network / no live LLM)."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "examples"
MANUFACTURING = EXAMPLES / "manufacturing.native.yaml"


@pytest.fixture(scope="module")
def manufacturing_engine():
    import ontographia

    return ontographia.Engine.load(str(MANUFACTURING))


@pytest.fixture(scope="module")
def manufacturing_schema(manufacturing_engine):
    return manufacturing_engine.intent_json_schema()


@pytest.fixture(scope="module")
def manufacturing_ontology(manufacturing_engine):
    return manufacturing_engine.ontology_json()
