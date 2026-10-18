"""Shared fixtures for ontographia.mcp tests (no network)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "examples"
MANUFACTURING = EXAMPLES / "manufacturing.native.yaml"

SAMPLE_INTENT = {
    "start": {"class": "Product", "alias": "product"},
    "traverse": [
        {
            "relationship": "has_part",
            "direction": "out",
            "to": {"class": "Part", "alias": "part"},
        },
        {
            "relationship": "supplied_by",
            "direction": "out",
            "to": {"class": "Supplier", "alias": "supplier"},
        },
    ],
    "filter": [
        {"alias": "product", "property": "sku", "op": "eq", "value": "SPX-100"}
    ],
    "return": [
        {"alias": "supplier", "property": "name", "as_name": "supplier_name"}
    ],
    "limit": 20,
}


class FakeNeo4jRunner:
    """In-memory Neo4j stand-in; records calls for assertions."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows if rows is not None else [{"supplier_name": "Acme"}]
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def run_read(
        self,
        query: str,
        params: dict[str, Any],
        *,
        database: str | None,
        row_limit: int,
    ) -> list[dict[str, Any]]:
        # Mirror production: deny writes before "running".
        from ontographia.mcp.safety import assert_read_only_cypher

        assert_read_only_cypher(query)
        self.calls.append(
            {
                "query": query,
                "params": params,
                "database": database,
                "row_limit": row_limit,
            }
        )
        return self.rows[:row_limit]

    def close(self) -> None:
        self.closed = True


@pytest.fixture(scope="module")
def manufacturing_engine():
    import ontographia

    return ontographia.Engine.load(str(MANUFACTURING))


@pytest.fixture
def mcp_tools(manufacturing_engine):
    from ontographia.mcp.config import McpConfig
    from ontographia.mcp.server import OntographiaMcp

    runner = FakeNeo4jRunner()
    tools = OntographiaMcp(
        McpConfig(
            ontology_paths=(MANUFACTURING,),
            neo4j_uri="bolt://localhost:7687",
            neo4j_username="neo4j",
            neo4j_password="test",
            neo4j_database="neo4j",
            row_limit=50,
        ),
        engine=manufacturing_engine,
        runner=runner,
    )
    tools._fake_runner = runner  # type: ignore[attr-defined]
    return tools
