"""Config / CLI parsing tests (no MCP stdio loop)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.python.mcp.conftest import MANUFACTURING


def test_load_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from ontographia.mcp.config import load_config_from_env

    monkeypatch.setenv("ONTOGRAPHIA_ONTOLOGY", str(MANUFACTURING))
    monkeypatch.setenv("NEO4J_URI", "bolt://db:7687")
    monkeypatch.setenv("NEO4J_USERNAME", "alice")
    monkeypatch.setenv("NEO4J_PASSWORD", "s3cret")
    monkeypatch.setenv("NEO4J_DATABASE", "analytics")
    monkeypatch.setenv("ONTOGRAPHIA_MCP_ROW_LIMIT", "25")

    cfg = load_config_from_env()
    assert cfg.primary_ontology == MANUFACTURING
    assert cfg.neo4j_uri == "bolt://db:7687"
    assert cfg.neo4j_username == "alice"
    assert cfg.neo4j_password == "s3cret"
    assert cfg.neo4j_database == "analytics"
    assert cfg.row_limit == 25
    assert cfg.neo4j_configured is True


def test_neo4j_user_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    from ontographia.mcp.config import load_config_from_env

    monkeypatch.delenv("NEO4J_USERNAME", raising=False)
    monkeypatch.setenv("NEO4J_USER", "bob")
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_PASSWORD", "x")
    cfg = load_config_from_env(ontology_paths=[MANUFACTURING])
    assert cfg.neo4j_username == "bob"


def test_cli_resolve_config_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from ontographia.mcp.__main__ import build_parser, resolve_config

    monkeypatch.setenv("NEO4J_URI", "bolt://env:7687")
    monkeypatch.setenv("NEO4J_USER", "envuser")
    monkeypatch.setenv("NEO4J_PASSWORD", "envpass")
    args = build_parser().parse_args(
        [
            "--ontology",
            str(MANUFACTURING),
            "--neo4j-uri",
            "bolt://cli:7687",
            "--neo4j-user",
            "cliuser",
            "--neo4j-password",
            "clipass",
            "--row-limit",
            "7",
        ]
    )
    cfg = resolve_config(args)
    assert cfg.neo4j_uri == "bolt://cli:7687"
    assert cfg.neo4j_username == "cliuser"
    assert cfg.neo4j_password == "clipass"
    assert cfg.row_limit == 7
    assert cfg.primary_ontology == Path(MANUFACTURING)


def test_main_missing_ontology_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    from ontographia.mcp.__main__ import main

    monkeypatch.delenv("ONTOGRAPHIA_ONTOLOGY", raising=False)
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_entry_point_importable() -> None:
    from ontographia.mcp.__main__ import main

    assert callable(main)
