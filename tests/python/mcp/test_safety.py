"""Write-query rejection policy tests (layer 3 of defense-in-depth)."""

from __future__ import annotations

import pytest

from ontographia.mcp.safety import (
    WriteQueryRejected,
    assert_read_only_cypher,
    find_write_constructs,
)

READ_ONLY = """
CYPHER 25
MATCH (product:Product)-[:has_part]->(part:Part)
FILTER product.sku = $param_0
RETURN part.part_number AS part_number
LIMIT 20
"""


@pytest.mark.parametrize(
    "cypher",
    [
        "CREATE (n:Product {sku: 'x'})",
        "MATCH (n) MERGE (n)-[:has_part]->(p:Part)",
        "MATCH (n) DELETE n",
        "MATCH (n) DETACH DELETE n",
        "MATCH (n) SET n.name = 'x'",
        "MATCH (n) REMOVE n.name",
        "DROP CONSTRAINT foo IF EXISTS",
        "LOAD CSV FROM 'file:///x.csv' AS row RETURN row",
        "MATCH (n) CALL { WITH n CREATE (n)-[:x]->() } IN TRANSACTIONS",
        "CALL apoc.create.node(['Product'], {sku:'x'})",
        "CALL apoc.merge.node(['Product'], {sku:'x'}, {}, {})",
        "CALL apoc.periodic.iterate('MATCH (n) RETURN n', 'DELETE n', {})",
        "CALL apoc.cypher.doIt('CREATE (n)', {})",
        "CALL gds.graph.project.mutate('g', ...)",  # mutate keyword in pattern
    ],
)
def test_write_constructs_denied(cypher: str) -> None:
    assert find_write_constructs(cypher)
    with pytest.raises(WriteQueryRejected, match="read-only|Refusing"):
        assert_read_only_cypher(cypher)


def test_read_only_allowed() -> None:
    assert find_write_constructs(READ_ONLY) == []
    assert_read_only_cypher(READ_ONLY)  # does not raise


def test_created_at_property_not_false_positive() -> None:
    # Word-boundary: ``created_at`` must not match ``CREATE``.
    cypher = "MATCH (n) RETURN n.created_at AS created_at"
    assert find_write_constructs(cypher) == []
    assert_read_only_cypher(cypher)


def test_create_inside_string_ignored() -> None:
    cypher = "MATCH (n) WHERE n.note = 'please CREATE nothing' RETURN n"
    assert find_write_constructs(cypher) == []
