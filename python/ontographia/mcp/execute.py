"""Read-only Neo4j execution helpers for the MCP ``execute`` tool."""

from __future__ import annotations

from typing import Any, Protocol

from neo4j import READ_ACCESS, GraphDatabase

from ontographia.mcp.config import McpConfig
from ontographia.mcp.safety import assert_read_only_cypher


class Neo4jRunner(Protocol):
    """Minimal protocol so tests can inject a fake runner."""

    def run_read(
        self,
        query: str,
        params: dict[str, Any],
        *,
        database: str | None,
        row_limit: int,
    ) -> list[dict[str, Any]]: ...

    def close(self) -> None: ...


class Neo4jDriverRunner:
    """Execute Cypher with READ access mode + ``execute_read`` transactions."""

    def __init__(self, uri: str, username: str, password: str) -> None:
        self._driver = GraphDatabase.driver(uri, auth=(username, password))

    def run_read(
        self,
        query: str,
        params: dict[str, Any],
        *,
        database: str | None,
        row_limit: int,
    ) -> list[dict[str, Any]]:
        assert_read_only_cypher(query)
        session_kwargs: dict[str, Any] = {"default_access_mode": READ_ACCESS}
        if database:
            session_kwargs["database"] = database

        def _work(tx: Any) -> list[dict[str, Any]]:
            result = tx.run(query, params)
            rows: list[dict[str, Any]] = []
            for i, record in enumerate(result):
                if i >= row_limit:
                    break
                rows.append(dict(record))
            return rows

        with self._driver.session(**session_kwargs) as session:
            return session.execute_read(_work)

    def close(self) -> None:
        self._driver.close()


def runner_from_config(config: McpConfig) -> Neo4jDriverRunner | None:
    if not config.neo4j_configured:
        return None
    assert config.neo4j_uri and config.neo4j_username is not None and config.neo4j_password is not None
    return Neo4jDriverRunner(config.neo4j_uri, config.neo4j_username, config.neo4j_password)
