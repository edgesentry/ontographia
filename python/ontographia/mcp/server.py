"""Ontographia MCP server (FastMCP-style ``MCPServer`` tools).

Uses the official ``mcp`` Python SDK. In mcp 2.x the FastMCP class was renamed
to :class:`mcp.server.mcpserver.MCPServer`; the decorator API is the same.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import ontographia

try:
    # mcp 2.x: FastMCP was renamed to MCPServer (same decorator API).
    from mcp.server.mcpserver import MCPServer
except ImportError:  # pragma: no cover - mcp 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer  # type: ignore[no-redef]

from ontographia.mcp.config import McpConfig
from ontographia.mcp.execute import Neo4jRunner, runner_from_config
from ontographia.mcp.safety import WriteQueryRejected, assert_read_only_cypher


def _summarize_ontology(ontology: dict[str, Any], *, sources: list[str]) -> dict[str, Any]:
    classes = [
        {"name": c.get("name"), "description": c.get("description")}
        for c in ontology.get("classes", [])
        if isinstance(c, dict)
    ]
    relationships = []
    for r in ontology.get("relationships", []):
        if not isinstance(r, dict):
            continue
        relationships.append(
            {
                "name": r.get("name"),
                "from_class": r.get("from_class"),
                "to_class": r.get("to_class"),
                "description": r.get("description"),
            }
        )
    properties = []
    for p in ontology.get("properties", []):
        if not isinstance(p, dict):
            continue
        properties.append(
            {
                "name": p.get("name"),
                "owner_class": p.get("owner_class"),
                "datatype": p.get("datatype"),
                "required": p.get("required", False),
                "unique": p.get("unique", False),
            }
        )
    return {
        "sources": sources,
        "classes": classes,
        "relationships": relationships,
        "properties": properties,
        "class_names": [c["name"] for c in classes if c.get("name")],
        "relationship_names": [r["name"] for r in relationships if r.get("name")],
    }


def _parse_intent(intent: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(intent, str):
        try:
            parsed = json.loads(intent)
        except json.JSONDecodeError as exc:
            raise ValueError(f"intent must be a JSON object string: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("intent JSON must be an object")
        return parsed
    if not isinstance(intent, dict):
        raise ValueError("intent must be a JSON object (dict) or JSON object string")
    return intent


class OntographiaMcp:
    """In-process tool implementations (also registered on the MCP server)."""

    def __init__(
        self,
        config: McpConfig,
        *,
        engine: Any | None = None,
        runner: Neo4jRunner | None = None,
    ) -> None:
        if not config.ontology_paths:
            raise ValueError(
                "No ontology configured. Pass --ontology PATH or set ONTOGRAPHIA_ONTOLOGY."
            )
        if len(config.ontology_paths) > 1:
            # Phase 1: single COM / Engine. Extra paths are rejected explicitly
            # so agents do not silently ignore additional ontologies.
            raise ValueError(
                "Multiple ontology paths are not supported yet; pass a single "
                f"ontology file (got {len(config.ontology_paths)})."
            )
        self.config = config
        path = config.primary_ontology
        self.engine = engine if engine is not None else ontographia.Engine.load(str(path))
        self._runner = runner
        self._owns_runner = False
        if self._runner is None and config.neo4j_configured:
            self._runner = runner_from_config(config)
            self._owns_runner = self._runner is not None

    def close(self) -> None:
        if self._owns_runner and self._runner is not None:
            self._runner.close()
            self._runner = None

    def list_ontology(self) -> dict[str, Any]:
        """Summarize classes, relationships, and properties of the loaded ontology."""
        ontology = self.engine.ontology_json()
        sources = [str(p) for p in self.config.ontology_paths]
        return _summarize_ontology(ontology, sources=sources)

    def intent_schema(self) -> dict[str, Any]:
        """Return the Intent JSON Schema constrained to the loaded ontology.

        MCP clients / LLMs must emit Intent JSON matching this schema. Never
        emit Cypher directly.
        """
        return self.engine.intent_json_schema()

    def build_cypher(
        self,
        intent: dict[str, Any] | str,
        *,
        dialect: str | None = None,
    ) -> dict[str, Any]:
        """Validate Intent JSON and emit Cypher 25 + parameters.

        On success::

            {"ok": True, "query": "...", "params": {...}, "dialect": "cypher25"}

        On validation / emission failure (structured for LLM repair)::

            {"ok": False, "errors": [{"message": "..."}]}
        """
        try:
            intent_obj = _parse_intent(intent)
            used_dialect = dialect or self.config.dialect
            result = self.engine.build(intent_obj, dialect=used_dialect)
            query = result["query"]
            params = dict(result["params"])
            # Defense-in-depth even for build-only: surface write detection early.
            try:
                assert_read_only_cypher(query)
            except WriteQueryRejected as exc:
                return {
                    "ok": False,
                    "errors": [{"message": str(exc), "code": "write_rejected"}],
                    "query": query,
                    "params": params,
                }
            return {
                "ok": True,
                "query": query,
                "params": params,
                "dialect": used_dialect,
            }
        except Exception as exc:  # ValueError from bindings / intent parse
            return {"ok": False, "errors": [{"message": str(exc)}]}

    def execute(
        self,
        intent: dict[str, Any] | str,
        *,
        dialect: str | None = None,
        row_limit: int | None = None,
    ) -> dict[str, Any]:
        """Build Cypher from Intent and run it read-only against Neo4j.

        Safety:

        1. Only Ontographia-generated Cypher is executed (never client Cypher).
        2. Neo4j session uses READ access mode / ``execute_read``.
        3. Generated query is deny-checked for write clauses before run.
        """
        if self._runner is None:
            return {
                "ok": False,
                "errors": [
                    {
                        "message": (
                            "Neo4j is not configured. Set NEO4J_URI, "
                            "NEO4J_USERNAME (or NEO4J_USER), and NEO4J_PASSWORD "
                            "(optional NEO4J_DATABASE), or pass matching CLI flags."
                        ),
                        "code": "neo4j_not_configured",
                    }
                ],
            }

        built = self.build_cypher(intent, dialect=dialect)
        if not built.get("ok"):
            return built

        query = built["query"]
        params = built["params"]
        limit = row_limit if row_limit is not None else self.config.row_limit
        try:
            assert_read_only_cypher(query)
            rows = self._runner.run_read(
                query,
                params,
                database=self.config.neo4j_database,
                row_limit=limit,
            )
            return {
                "ok": True,
                "query": query,
                "params": params,
                "rows": rows,
                "row_count": len(rows),
                "row_limit": limit,
                "truncated": len(rows) >= limit,
            }
        except WriteQueryRejected as exc:
            return {
                "ok": False,
                "errors": [{"message": str(exc), "code": "write_rejected"}],
                "query": query,
                "params": params,
            }
        except Exception as exc:
            return {
                "ok": False,
                "errors": [{"message": str(exc), "code": "neo4j_error"}],
                "query": query,
                "params": params,
            }


def create_mcp_server(
    config: McpConfig,
    *,
    engine: Any | None = None,
    runner: Neo4jRunner | None = None,
) -> tuple[MCPServer[Any], OntographiaMcp]:
    """Create an MCPServer with Ontographia tools registered."""
    tools = OntographiaMcp(config, engine=engine, runner=runner)
    sources = ", ".join(str(p) for p in config.ontology_paths) or "(none)"
    mcp = MCPServer(
        name="ontographia",
        instructions=(
            "Ontographia MCP: turn natural-language graph questions into "
            "ontology-validated Intent JSON, then into parameter-bound Cypher 25. "
            "Never write Cypher yourself — call intent_schema, emit Intent JSON, "
            "then build_cypher or execute. Loaded ontology: "
            f"{sources}."
        ),
    )

    @mcp.tool(
        name="list_ontology",
        description=(
            "Summarize classes, relationships, and properties of the loaded "
            "ontology. Use these names in Intent JSON (never invent labels)."
        ),
    )
    def list_ontology() -> dict[str, Any]:
        return tools.list_ontology()

    @mcp.tool(
        name="intent_schema",
        description=(
            "Return the Intent JSON Schema constrained to the loaded ontology. "
            "The client LLM must emit Intent JSON matching this schema — never "
            "raw Cypher, SQL, or other query languages."
        ),
    )
    def intent_schema() -> dict[str, Any]:
        return tools.intent_schema()

    @mcp.tool(
        name="build_cypher",
        description=(
            "Validate Intent JSON against the ontology and emit Cypher 25 with "
            "bound parameters. Returns {ok, query, params} or {ok: false, errors} "
            "suitable for LLM repair. Does not execute against Neo4j."
        ),
    )
    def build_cypher(
        intent: dict[str, Any],
        dialect: str | None = None,
    ) -> dict[str, Any]:
        return tools.build_cypher(intent, dialect=dialect)

    @mcp.tool(
        name="execute",
        description=(
            "Build Cypher from Intent JSON via Ontographia and run it read-only "
            "against Neo4j. Never accepts raw Cypher. Returns rows with a row "
            "limit. Fails clearly if Neo4j is not configured or if the generated "
            "query looks like a write."
        ),
    )
    def execute(
        intent: dict[str, Any],
        dialect: str | None = None,
        row_limit: int | None = None,
    ) -> dict[str, Any]:
        return tools.execute(intent, dialect=dialect, row_limit=row_limit)

    return mcp, tools


def create_server_from_paths(
    ontology: str | Path | list[str | Path],
    **kwargs: Any,
) -> tuple[MCPServer[Any], OntographiaMcp]:
    """Convenience wrapper used by tests and programmatic embedding."""
    if isinstance(ontology, (str, Path)):
        paths = [ontology]
    else:
        paths = list(ontology)
    from ontographia.mcp.config import load_config_from_env

    config = load_config_from_env(ontology_paths=paths, **{
        k: kwargs[k]
        for k in ("row_limit", "dialect")
        if k in kwargs
    })
    # Allow overriding Neo4j fields for tests without env pollution.
    if any(k.startswith("neo4j_") for k in kwargs):
        config = McpConfig(
            ontology_paths=config.ontology_paths,
            neo4j_uri=kwargs.get("neo4j_uri", config.neo4j_uri),
            neo4j_username=kwargs.get("neo4j_username", config.neo4j_username),
            neo4j_password=kwargs.get("neo4j_password", config.neo4j_password),
            neo4j_database=kwargs.get("neo4j_database", config.neo4j_database),
            row_limit=kwargs.get("row_limit", config.row_limit),
            dialect=kwargs.get("dialect", config.dialect),
        )
    return create_mcp_server(
        config,
        engine=kwargs.get("engine"),
        runner=kwargs.get("runner"),
    )
