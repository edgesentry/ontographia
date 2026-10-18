"""Console entry point: ``ontographia-mcp`` / ``python -m ontographia.mcp``."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ontographia.mcp.config import DEFAULT_ROW_LIMIT, McpConfig, load_config_from_env
from ontographia.mcp.server import create_mcp_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ontographia-mcp",
        description=(
            "Ontographia MCP server (stdio by default). "
            "Agents use Intent JSON tools — never send raw Cypher."
        ),
    )
    parser.add_argument(
        "--ontology",
        action="append",
        dest="ontologies",
        metavar="PATH",
        help=(
            "Ontology file path (native YAML, TTL, JSON-LD, LinkML, OBO, …). "
            "Required unless ONTOGRAPHIA_ONTOLOGY is set. "
            "Repeatable, but only a single path is supported in this release."
        ),
    )
    parser.add_argument(
        "--neo4j-uri",
        default=None,
        help="Neo4j bolt URI (default: NEO4J_URI). Required for the execute tool.",
    )
    parser.add_argument(
        "--neo4j-user",
        default=None,
        help="Neo4j username (default: NEO4J_USERNAME or NEO4J_USER).",
    )
    parser.add_argument(
        "--neo4j-password",
        default=None,
        help="Neo4j password (default: NEO4J_PASSWORD).",
    )
    parser.add_argument(
        "--neo4j-database",
        default=None,
        help="Neo4j database name (default: NEO4J_DATABASE / driver default).",
    )
    parser.add_argument(
        "--row-limit",
        type=int,
        default=None,
        help=f"Max rows returned by execute (default: {DEFAULT_ROW_LIMIT} / ONTOGRAPHIA_MCP_ROW_LIMIT).",
    )
    parser.add_argument(
        "--dialect",
        default=None,
        help="Cypher dialect for build/execute (default: cypher25 / ONTOGRAPHIA_DIALECT).",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio",),
        default="stdio",
        help="MCP transport (only stdio is supported in this release).",
    )
    return parser


def resolve_config(args: argparse.Namespace) -> McpConfig:
    base = load_config_from_env(
        ontology_paths=args.ontologies,
        row_limit=args.row_limit,
        dialect=args.dialect,
    )
    return McpConfig(
        ontology_paths=base.ontology_paths,
        neo4j_uri=args.neo4j_uri or base.neo4j_uri,
        neo4j_username=args.neo4j_user or base.neo4j_username,
        neo4j_password=args.neo4j_password or base.neo4j_password,
        neo4j_database=args.neo4j_database or base.neo4j_database,
        row_limit=args.row_limit if args.row_limit is not None else base.row_limit,
        dialect=args.dialect or base.dialect,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = resolve_config(args)
    except Exception as exc:
        print(f"ontographia-mcp: configuration error: {exc}", file=sys.stderr)
        return 2

    if not config.ontology_paths:
        parser.error(
            "ontology path required (--ontology PATH or ONTOGRAPHIA_ONTOLOGY)"
        )

    for path in config.ontology_paths:
        if not Path(path).is_file():
            print(f"ontographia-mcp: ontology file not found: {path}", file=sys.stderr)
            return 2

    try:
        mcp, tools = create_mcp_server(config)
    except Exception as exc:
        print(f"ontographia-mcp: failed to start: {exc}", file=sys.stderr)
        return 1

    # Avoid noisy MCP logs on stdout (stdio transport uses stdout for JSON-RPC).
    os.environ.setdefault("MCP_DISABLE_BANNER", "1")

    try:
        mcp.run(transport=args.transport)
    finally:
        tools.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
