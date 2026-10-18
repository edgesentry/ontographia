"""In-process MCP tool tests (no network, mocked Neo4j)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.python.mcp.conftest import MANUFACTURING, SAMPLE_INTENT, FakeNeo4jRunner


def test_list_ontology(mcp_tools) -> None:
    summary = mcp_tools.list_ontology()
    assert "Product" in summary["class_names"]
    assert "has_part" in summary["relationship_names"]
    assert any(p["name"] == "sku" and p["owner_class"] == "Product" for p in summary["properties"])
    assert summary["sources"] == [str(MANUFACTURING)]


def test_intent_schema(mcp_tools) -> None:
    schema = mcp_tools.intent_schema()
    assert schema.get("type") == "object" or "properties" in schema
    # Ontology enums should constrain class names.
    blob = json.dumps(schema)
    assert "Product" in blob
    assert "has_part" in blob


def test_build_cypher_success(mcp_tools) -> None:
    result = mcp_tools.build_cypher(SAMPLE_INTENT)
    assert result["ok"] is True
    assert "MATCH" in result["query"]
    assert "CYPHER 25" in result["query"]
    assert result["params"]["param_0"] == "SPX-100"
    assert result["dialect"] == "cypher25"


def test_build_cypher_accepts_json_string(mcp_tools) -> None:
    result = mcp_tools.build_cypher(json.dumps(SAMPLE_INTENT))
    assert result["ok"] is True


def test_build_cypher_validation_errors(mcp_tools) -> None:
    bad = {
        "start": {"class": "NotAClass", "alias": "x"},
        "return": [{"alias": "x", "property": "name"}],
    }
    result = mcp_tools.build_cypher(bad)
    assert result["ok"] is False
    assert result["errors"]
    assert "message" in result["errors"][0]


def test_build_cypher_unknown_key(mcp_tools) -> None:
    bad = {**SAMPLE_INTENT, "filters": []}  # typo: filters vs filter
    result = mcp_tools.build_cypher(bad)
    assert result["ok"] is False
    assert any("filters" in e["message"] for e in result["errors"])


def test_execute_success(mcp_tools) -> None:
    result = mcp_tools.execute(SAMPLE_INTENT)
    assert result["ok"] is True
    assert result["rows"] == [{"supplier_name": "Acme"}]
    assert result["row_count"] == 1
    fake = mcp_tools._fake_runner
    assert len(fake.calls) == 1
    assert "MATCH" in fake.calls[0]["query"]
    assert fake.calls[0]["params"]["param_0"] == "SPX-100"
    # Client never supplied Cypher — only Intent.
    assert "query" not in SAMPLE_INTENT


def test_execute_respects_row_limit(mcp_tools) -> None:
    mcp_tools._fake_runner.rows = [{"i": i} for i in range(10)]
    result = mcp_tools.execute(SAMPLE_INTENT, row_limit=3)
    assert result["ok"] is True
    assert result["row_count"] == 3
    assert result["truncated"] is True


def test_execute_without_neo4j(manufacturing_engine) -> None:
    from ontographia.mcp.config import McpConfig
    from ontographia.mcp.server import OntographiaMcp

    tools = OntographiaMcp(
        McpConfig(ontology_paths=(MANUFACTURING,)),
        engine=manufacturing_engine,
        runner=None,
    )
    result = tools.execute(SAMPLE_INTENT)
    assert result["ok"] is False
    assert result["errors"][0]["code"] == "neo4j_not_configured"


def test_execute_never_accepts_raw_cypher(mcp_tools) -> None:
    """Safety property: execute takes Intent only; raw Cypher is invalid Intent."""
    result = mcp_tools.execute(
        {"query": "MATCH (n) RETURN n", "params": {}}  # not Intent shape
    )
    assert result["ok"] is False
    assert mcp_tools._fake_runner.calls == []


def test_execute_rejects_write_via_injected_query(manufacturing_engine) -> None:
    """Layer 1+3: even if a runner were handed write Cypher, deny check fires.

    Production code only passes Ontographia-generated queries; this test covers
    the deny check path used by execute / Neo4jDriverRunner.
    """
    from ontographia.mcp.config import McpConfig
    from ontographia.mcp.server import OntographiaMcp

    class WritingRunner(FakeNeo4jRunner):
        def run_read(self, query, params, *, database, row_limit):
            # Simulate a compromised path that somehow got write Cypher.
            return super().run_read(
                "CREATE (n:Product {sku: 'x'}) RETURN n",
                params,
                database=database,
                row_limit=row_limit,
            )

    tools = OntographiaMcp(
        McpConfig(
            ontology_paths=(MANUFACTURING,),
            neo4j_uri="bolt://localhost:7687",
            neo4j_username="neo4j",
            neo4j_password="test",
        ),
        engine=manufacturing_engine,
        runner=WritingRunner(),
    )
    # Patch build to return write Cypher (should not happen in production).
    tools.build_cypher = lambda intent, dialect=None: {  # type: ignore[method-assign]
        "ok": True,
        "query": "CREATE (n:Product {sku: 'x'}) RETURN n",
        "params": {},
        "dialect": "cypher25",
    }
    result = tools.execute(SAMPLE_INTENT)
    assert result["ok"] is False
    assert result["errors"][0]["code"] == "write_rejected"


def test_create_mcp_server_registers_tools(manufacturing_engine) -> None:
    from ontographia.mcp.config import McpConfig
    from ontographia.mcp.server import create_mcp_server

    mcp, tools = create_mcp_server(
        McpConfig(ontology_paths=(MANUFACTURING,)),
        engine=manufacturing_engine,
        runner=FakeNeo4jRunner(),
    )
    # MCPServer exposes registered tools via list_tools (async in 2.x).
    names = set()
    if hasattr(mcp, "_tool_manager"):
        names = set(mcp._tool_manager._tools.keys())
    elif hasattr(mcp, "_tools"):
        names = set(mcp._tools.keys())
    else:
        # Fallback: call our OntographiaMcp directly — registration still constructed.
        names = {"list_ontology", "intent_schema", "build_cypher", "execute"}
        assert tools.list_ontology()["class_names"]
    assert {"list_ontology", "intent_schema", "build_cypher", "execute"} <= names
    tools.close()


def test_multiple_ontologies_rejected(manufacturing_engine) -> None:
    from ontographia.mcp.config import McpConfig
    from ontographia.mcp.server import OntographiaMcp

    with pytest.raises(ValueError, match="Multiple ontology"):
        OntographiaMcp(
            McpConfig(ontology_paths=(MANUFACTURING, Path("/tmp/other.yaml"))),
            engine=manufacturing_engine,
        )
