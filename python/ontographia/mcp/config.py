"""CLI / environment configuration for the Ontographia MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_ROW_LIMIT = 100


@dataclass(frozen=True)
class McpConfig:
    """Runtime settings for :class:`~ontographia.mcp.server.OntographiaMcp`.

    Neo4j fields may be unset; in that case ``build_cypher`` / ``list_ontology`` /
    ``intent_schema`` still work, but ``execute`` returns a clear configuration
    error.
    """

    ontology_paths: tuple[Path, ...]
    neo4j_uri: str | None = None
    neo4j_username: str | None = None
    neo4j_password: str | None = None
    neo4j_database: str | None = None
    row_limit: int = DEFAULT_ROW_LIMIT
    dialect: str = "cypher25"

    @property
    def neo4j_configured(self) -> bool:
        return bool(self.neo4j_uri and self.neo4j_username is not None and self.neo4j_password is not None)

    @property
    def primary_ontology(self) -> Path:
        if not self.ontology_paths:
            raise ValueError("At least one ontology path is required")
        return self.ontology_paths[0]


def _env_first(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value != "":
            return value
    return None


def load_config_from_env(
    *,
    ontology_paths: list[str | Path] | None = None,
    row_limit: int | None = None,
    dialect: str | None = None,
) -> McpConfig:
    """Build :class:`McpConfig` from explicit paths plus standard env vars.

    Ontology paths (first non-empty wins):

    * ``ontology_paths`` argument
    * ``ONTOGRAPHIA_ONTOLOGY`` (``os.pathsep``-separated list)

    Neo4j (optional):

    * ``NEO4J_URI``
    * ``NEO4J_USERNAME`` or ``NEO4J_USER``
    * ``NEO4J_PASSWORD``
    * ``NEO4J_DATABASE`` (optional; driver default when unset)

    Row limit: ``ONTOGRAPHIA_MCP_ROW_LIMIT`` (default 100).
    """
    paths: list[Path] = []
    if ontology_paths:
        paths = [Path(p) for p in ontology_paths]
    else:
        raw = _env_first("ONTOGRAPHIA_ONTOLOGY")
        if raw:
            paths = [Path(p) for p in raw.split(os.pathsep) if p]

    limit = row_limit
    if limit is None:
        env_limit = _env_first("ONTOGRAPHIA_MCP_ROW_LIMIT")
        limit = int(env_limit) if env_limit else DEFAULT_ROW_LIMIT

    return McpConfig(
        ontology_paths=tuple(paths),
        neo4j_uri=_env_first("NEO4J_URI"),
        neo4j_username=_env_first("NEO4J_USERNAME", "NEO4J_USER"),
        neo4j_password=_env_first("NEO4J_PASSWORD"),
        neo4j_database=_env_first("NEO4J_DATABASE"),
        row_limit=limit,
        dialect=dialect or _env_first("ONTOGRAPHIA_DIALECT") or "cypher25",
    )
