"""CLI smoke tests for `otg` (no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ontographia.cli import main

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "examples"
MANUFACTURING = EXAMPLES / "manufacturing.native.yaml"
SAMPLE_INTENT = EXAMPLES / "sample_intent.json"
MOVIES = EXAMPLES / "movies.native.yaml"
MATRIX = EXAMPLES / "movies_matrix.json"
FORMULA = ROOT / "packaging" / "homebrew" / "otg.rb"


def test_help_mentions_build_and_read_only_execute(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "build" in out
    assert "execute" in out
    assert "read-only" in out
    assert "Intent" in out


def test_build_smoke(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "build",
            "--ontology",
            str(MANUFACTURING),
            "--intent",
            str(SAMPLE_INTENT),
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "CYPHER 25" in out
    assert "MATCH" in out
    assert "param_0" in out
    assert "SPX-100" in out
    assert "CREATE" not in out


def test_build_json(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "build",
            "--ontology",
            str(MANUFACTURING),
            "--intent",
            str(SAMPLE_INTENT),
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["params"]["param_0"] == "SPX-100"
    assert "FILTER" in payload["query"]


def test_movies_matrix_build(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "build",
            "--ontology",
            str(MOVIES),
            "--intent",
            str(MATRIX),
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert "ACTED_IN" in payload["query"]
    assert payload["params"]["param_0"] == "The Matrix"
    assert "ORDER BY actor" in payload["query"]
    assert "CREATE" not in payload["query"]
    assert "MERGE" not in payload["query"]


def test_execute_without_neo4j_is_config_error(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_USER", "NEO4J_PASSWORD", "NEO4J_DATABASE"):
        monkeypatch.delenv(name, raising=False)
    code = main(
        [
            "execute",
            "--ontology",
            str(MANUFACTURING),
            "--intent",
            str(SAMPLE_INTENT),
        ]
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "Neo4j is not configured" in err


def test_execute_rejects_write_and_does_not_run(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defense in depth: a generated write query is refused before the driver runs."""

    class _FakeEngine:
        def build(self, intent: object, dialect: str = "cypher25") -> dict[str, object]:
            del intent, dialect
            return {"query": "CREATE (n:X {name: 'nope'}) RETURN n", "params": {}}

    class _Runner:
        def __init__(self) -> None:
            self.calls = 0
            self.closed = False

        def run_read(self, query: str, params: dict, *, database: str | None, row_limit: int):
            del query, params, database, row_limit
            self.calls += 1
            raise AssertionError("write Cypher must not be executed")

        def close(self) -> None:
            self.closed = True

    runner = _Runner()
    monkeypatch.setattr("ontographia.Engine.load", lambda path: _FakeEngine())
    monkeypatch.setattr("ontographia.mcp.execute.runner_from_config", lambda config: runner)

    code = main(
        [
            "execute",
            "--ontology",
            str(MANUFACTURING),
            "--intent",
            str(SAMPLE_INTENT),
            "--neo4j-uri",
            "bolt://127.0.0.1:7687",
            "--neo4j-user",
            "neo4j",
            "--neo4j-password",
            "secret",
        ]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert runner.calls == 0
    assert runner.closed is True
    assert "read-only" in captured.err
    assert "CREATE" not in captured.out
    assert "secret" not in captured.out
    assert "secret" not in captured.err


def test_execute_rejects_raw_cypher_intent(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    raw = tmp_path / "not_intent.json"
    raw.write_text(json.dumps({"query": "CREATE (n:X) RETURN n"}), encoding="utf-8")

    class _Runner:
        def __init__(self) -> None:
            self.calls = 0

        def run_read(self, *args: object, **kwargs: object) -> list[dict]:
            del args, kwargs
            self.calls += 1
            return []

        def close(self) -> None:
            return None

    runner = _Runner()
    monkeypatch.setattr("ontographia.mcp.execute.runner_from_config", lambda config: runner)
    code = main(
        [
            "execute",
            "--ontology",
            str(MANUFACTURING),
            "--intent",
            str(raw),
            "--neo4j-uri",
            "bolt://127.0.0.1:7687",
            "--neo4j-user",
            "neo4j",
            "--neo4j-password",
            "secret",
        ]
    )
    assert code == 1
    assert runner.calls == 0
    err = capsys.readouterr().err
    assert "secret" not in err


def test_homebrew_formula_is_otg_not_mcp() -> None:
    text = FORMULA.read_text(encoding="utf-8")
    assert "class Otg < Formula" in text
    assert 'depends_on "uv"' in text
    assert 'PYPI_SPEC = "ontographia[cli]"' in text
    assert "ontographia-mcp" in text
    assert "Do not bottle" in text
    assert "not part of this formula" in text
    assert "bin.install_symlink otg" in text
