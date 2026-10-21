"""Live Neo4j integration tests for the MCP ``execute`` tool.

Skipped unless ``NEO4J_URI`` is set (CI ``neo4j-integration`` job sets it).
Reuses seed + row expectations from ``scripts/neo4j_integration_test.py``.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from ontographia.llm.fixtures import MOCK_LLM_INTENTS
from tests.python.mcp.conftest import MANUFACTURING

ROOT = Path(__file__).resolve().parents[3]
SEED_FILE = ROOT / "examples" / "neo4j" / "seed.cypher"
PROBE_LABEL = "__OntographiaMcpWriteProbe"

pytestmark = [
    pytest.mark.neo4j,
    pytest.mark.skipif(
        not os.environ.get("NEO4J_URI"),
        reason="NEO4J_URI not set (live Neo4j integration)",
    ),
]


def _load_neo4j_script() -> Any:
    """Load scripts/neo4j_integration_test.py for shared CASES / load_seed."""
    path = ROOT / "scripts" / "neo4j_integration_test.py"
    name = "neo4j_integration_test"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so @dataclass can resolve cls.__module__.
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_neo4j_script = _load_neo4j_script()
CASES = _neo4j_script.CASES
load_seed = _neo4j_script.load_seed


def _normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: tuple(sorted(row.items())))


@pytest.fixture(scope="module")
def neo4j_auth() -> tuple[str, str, str]:
    uri = os.environ["NEO4J_URI"]
    user = os.environ.get("NEO4J_USER") or os.environ.get("NEO4J_USERNAME") or "neo4j"
    password = os.environ.get("NEO4J_PASSWORD", "ontographia")
    return uri, user, password


@pytest.fixture(scope="module")
def neo4j_driver(neo4j_auth: tuple[str, str, str]):
    from neo4j import GraphDatabase

    uri, user, password = neo4j_auth
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        driver.verify_connectivity()
    except Exception as exc:  # noqa: BLE001
        driver.close()
        pytest.fail(f"cannot connect to Neo4j at {uri}: {exc}")

    load_seed_flag = os.environ.get("NEO4J_LOAD_SEED", "1") not in {"0", "false", "no"}
    if load_seed_flag:
        if not SEED_FILE.is_file():
            driver.close()
            pytest.fail(f"seed file not found: {SEED_FILE}")
        load_seed(driver, SEED_FILE)

    yield driver
    driver.close()


@pytest.fixture(scope="module")
def mcp_live(neo4j_auth: tuple[str, str, str], neo4j_driver, manufacturing_engine):
    """MCP tools wired to the live Neo4j driver (seed loaded via neo4j_driver)."""
    del neo4j_driver  # ensure seed fixture runs first
    from ontographia.mcp.config import McpConfig
    from ontographia.mcp.server import OntographiaMcp

    uri, user, password = neo4j_auth
    tools = OntographiaMcp(
        McpConfig(
            ontology_paths=(MANUFACTURING,),
            neo4j_uri=uri,
            neo4j_username=user,
            neo4j_password=password,
            neo4j_database=os.environ.get("NEO4J_DATABASE"),
            row_limit=50,
        ),
        engine=manufacturing_engine,
    )
    yield tools
    tools.close()


def _probe_count(driver: Any) -> int:
    with driver.session() as session:
        record = session.run(f"MATCH (n:{PROBE_LABEL}) RETURN count(n) AS c").single()
        assert record is not None
        return int(record["c"])


def test_list_ontology_live(mcp_live) -> None:
    summary = mcp_live.list_ontology()
    assert "Product" in summary["class_names"]
    assert "has_part" in summary["relationship_names"]
    assert summary["sources"] == [str(MANUFACTURING)]


def test_intent_schema_live(mcp_live) -> None:
    schema = mcp_live.intent_schema()
    assert isinstance(schema, dict)
    assert schema.get("type") == "object" or "properties" in schema


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_build_and_execute_against_seed(mcp_live, case) -> None:
    intent = MOCK_LLM_INTENTS[case.user_question]

    built = mcp_live.build_cypher(intent)
    assert built["ok"] is True, built
    assert built["query"].startswith("CYPHER 25")
    assert "MATCH" in built["query"]

    result = mcp_live.execute(intent)
    assert result["ok"] is True, result
    assert result["query"].startswith("CYPHER 25")
    assert _normalize_rows(result["rows"]) == _normalize_rows(case.expected_rows)
    assert result["row_count"] == len(case.expected_rows)


def test_execute_write_rejected_does_not_mutate(
    mcp_live, neo4j_driver, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deny-list write rejection on the live execute path; DB must stay unchanged."""
    before = _probe_count(neo4j_driver)
    write_query = f"CREATE (n:{PROBE_LABEL} {{id: $id}}) RETURN n.id AS id"

    def _fake_build(intent: Any, dialect: str | None = None) -> dict[str, Any]:
        del intent, dialect
        return {
            "ok": True,
            "query": write_query,
            "params": {"id": "should-not-persist"},
            "dialect": "cypher25",
        }

    monkeypatch.setattr(mcp_live, "build_cypher", _fake_build)

    result = mcp_live.execute({"start": {"class": "Product", "alias": "p"}})
    assert result["ok"] is False
    assert result["errors"][0]["code"] == "write_rejected"
    assert _probe_count(neo4j_driver) == before


def test_driver_runner_write_rejected_does_not_mutate(neo4j_auth, neo4j_driver) -> None:
    """Neo4jDriverRunner deny check against the real driver; no mutation."""
    from ontographia.mcp.execute import Neo4jDriverRunner
    from ontographia.mcp.safety import WriteQueryRejected

    uri, user, password = neo4j_auth
    before = _probe_count(neo4j_driver)
    runner = Neo4jDriverRunner(uri, user, password)
    try:
        with pytest.raises(WriteQueryRejected):
            runner.run_read(
                f"CREATE (n:{PROBE_LABEL} {{id: $id}}) RETURN n",
                {"id": "should-not-persist"},
                database=os.environ.get("NEO4J_DATABASE"),
                row_limit=10,
            )
    finally:
        runner.close()
    assert _probe_count(neo4j_driver) == before


def test_neo4j_read_access_rejects_write(neo4j_driver) -> None:
    """Layer 2: Neo4j READ session itself refuses CREATE (defense in depth)."""
    from neo4j import READ_ACCESS
    from neo4j.exceptions import ClientError, Neo4jError

    before = _probe_count(neo4j_driver)

    def _write(tx: Any) -> None:
        tx.run(
            f"CREATE (n:{PROBE_LABEL} {{id: $id}}) RETURN n",
            id="should-not-persist",
        ).consume()

    with neo4j_driver.session(default_access_mode=READ_ACCESS) as session:
        with pytest.raises((ClientError, Neo4jError)):
            session.execute_read(_write)

    assert _probe_count(neo4j_driver) == before
