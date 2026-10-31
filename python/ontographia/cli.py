"""``otg`` — build Cypher from Intent JSON and optionally run it read-only.

The LLM never writes Cypher. ``otg build`` / ``otg execute`` call
``Engine.build`` and the same read-only policy as the MCP server
(:mod:`ontographia.mcp.read_only`, :mod:`ontographia.mcp.safety`,
:mod:`ontographia.mcp.execute`).
"""

from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from ontographia.mcp.config import DEFAULT_ROW_LIMIT, McpConfig, load_config_from_env
from ontographia.mcp.read_only import build_read_only, execute_read_only


def _package_version() -> str:
    try:
        return version("ontographia")
    except PackageNotFoundError:
        return "0.0.0"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="otg",
        description=(
            "Build parameter-bound Cypher from an ontology and Intent JSON, "
            "and optionally execute it read-only against Neo4j. "
            "Ontographia compiles the query; the LLM never writes Cypher."
        ),
    )
    parser.add_argument("--version", action="version", version=f"otg {_package_version()}")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser(
        "build",
        help="Compile Intent JSON to Cypher (no database connection)",
    )
    _add_compile_args(build)

    execute = sub.add_parser(
        "execute",
        help="Compile Intent JSON and run it read-only against Neo4j",
    )
    _add_compile_args(execute)
    execute.add_argument(
        "--neo4j-uri",
        default=None,
        help="Neo4j bolt URI (default: NEO4J_URI).",
    )
    execute.add_argument(
        "--neo4j-user",
        default=None,
        help="Neo4j username (default: NEO4J_USERNAME or NEO4J_USER).",
    )
    execute.add_argument(
        "--neo4j-password",
        default=None,
        help="Neo4j password (default: NEO4J_PASSWORD). Prefer the env var.",
    )
    execute.add_argument(
        "--neo4j-database",
        default=None,
        help="Neo4j database name (default: NEO4J_DATABASE / driver default).",
    )
    execute.add_argument(
        "--row-limit",
        type=int,
        default=None,
        help=(
            f"Max rows returned (default: {DEFAULT_ROW_LIMIT} / "
            "ONTOGRAPHIA_MCP_ROW_LIMIT). Also caps the Cypher LIMIT."
        ),
    )
    return parser


def _add_compile_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--ontology",
        default=None,
        metavar="PATH",
        help="Ontology file (default: ONTOGRAPHIA_ONTOLOGY). Format is auto-detected.",
    )
    parser.add_argument(
        "--intent",
        default=None,
        metavar="PATH",
        help="Intent JSON file. Omit or pass - to read stdin.",
    )
    parser.add_argument(
        "--dialect",
        default=None,
        help="Cypher dialect (default: cypher25 / ONTOGRAPHIA_DIALECT). cypher5 and gql also work.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a JSON object instead of text.",
    )


def resolve_config(args: argparse.Namespace) -> McpConfig:
    paths = [args.ontology] if getattr(args, "ontology", None) else None
    row_limit = getattr(args, "row_limit", None)
    base = load_config_from_env(
        ontology_paths=paths,
        row_limit=row_limit,
        dialect=args.dialect,
    )
    return McpConfig(
        ontology_paths=base.ontology_paths,
        neo4j_uri=getattr(args, "neo4j_uri", None) or base.neo4j_uri,
        neo4j_username=getattr(args, "neo4j_user", None) or base.neo4j_username,
        neo4j_password=getattr(args, "neo4j_password", None) or base.neo4j_password,
        neo4j_database=getattr(args, "neo4j_database", None) or base.neo4j_database,
        row_limit=row_limit if row_limit is not None else base.row_limit,
        dialect=args.dialect or base.dialect,
    )


def load_intent(path: str | None) -> dict[str, Any]:
    if path is None or path == "-":
        if path is None and sys.stdin.isatty():
            raise ValueError("pass --intent PATH or pipe Intent JSON on stdin")
        text = sys.stdin.read()
    else:
        intent_path = Path(path)
        if not intent_path.is_file():
            raise ValueError(f"intent file not found: {intent_path}")
        text = intent_path.read_text(encoding="utf-8")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"intent must be a JSON object: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("intent JSON must be an object")
    return parsed


def _engine(ontology: Path) -> Any:
    import ontographia

    return ontographia.Engine.load(str(ontology))


def _plain(value: Any) -> Any:
    """Make Neo4j driver values JSON-friendly."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    labels = getattr(value, "labels", None)
    if labels is not None and hasattr(value, "items"):
        return {"labels": sorted(str(label) for label in labels), "properties": _plain(dict(value))}
    iso = getattr(value, "iso_format", None)
    if callable(iso):
        return iso()
    return str(value)


def _emit_errors(result: dict[str, Any]) -> int:
    errors = result.get("errors") or [{"message": "unknown error"}]
    code = 1
    for err in errors:
        message = err.get("message", err)
        print(f"otg: {message}", file=sys.stderr)
        if err.get("code") == "neo4j_not_configured":
            code = 2
    return code


def _print_params(params: dict[str, Any]) -> None:
    print("params:")
    if not params:
        print("  (none)")
        return
    for key, value in params.items():
        print(f"  {key}: {json.dumps(_plain(value), ensure_ascii=False)}")


def _print_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("(no rows)")
        return
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                columns.append(str(key))
    rendered = []
    for row in rows:
        cells = []
        for column in columns:
            cell = _plain(row.get(column))
            if isinstance(cell, str):
                text = cell
            else:
                text = json.dumps(cell, ensure_ascii=False)
            cells.append(text.replace("\n", " "))
        rendered.append(cells)
    widths = [len(column) for column in columns]
    for cells in rendered:
        for index, cell in enumerate(cells):
            widths[index] = max(widths[index], len(cell))
    header = "  ".join(column.ljust(widths[i]) for i, column in enumerate(columns))
    rule = "  ".join("-" * widths[i] for i in range(len(columns)))
    print(header)
    print(rule)
    for cells in rendered:
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells)))


def _print_build(result: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps({k: _plain(v) for k, v in result.items()}, indent=2, ensure_ascii=False))
        return
    print(result["query"])
    print()
    _print_params(dict(result.get("params") or {}))


def _print_execute(result: dict[str, Any], *, as_json: bool) -> None:
    payload = {k: _plain(v) for k, v in result.items()}
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    print(payload["query"])
    print()
    _print_params(dict(payload.get("params") or {}))
    print()
    _print_table(list(payload.get("rows") or []))
    count = payload.get("row_count", 0)
    noun = "row" if count == 1 else "rows"
    line = f"{count} {noun}"
    if payload.get("truncated"):
        line += f" (truncated at {payload.get('row_limit')})"
    print()
    print(line)


def _checked_ontology(config: McpConfig) -> Path | None:
    if not config.ontology_paths:
        print(
            "otg: ontology path required (--ontology PATH or ONTOGRAPHIA_ONTOLOGY)",
            file=sys.stderr,
        )
        return None
    if len(config.ontology_paths) > 1:
        print(
            "otg: multiple ontology paths are not supported; pass a single file "
            f"(got {len(config.ontology_paths)}).",
            file=sys.stderr,
        )
        return None
    path = config.primary_ontology
    if not path.is_file():
        print(f"otg: ontology file not found: {path}", file=sys.stderr)
        return None
    return path


def _run_build(args: argparse.Namespace, config: McpConfig) -> int:
    ontology = _checked_ontology(config)
    if ontology is None:
        return 2
    try:
        intent = load_intent(args.intent)
    except ValueError as exc:
        print(f"otg: {exc}", file=sys.stderr)
        return 2
    try:
        engine = _engine(ontology)
    except Exception as exc:
        print(f"otg: failed to load ontology: {exc}", file=sys.stderr)
        return 1
    result = build_read_only(engine, intent, dialect=config.dialect)
    if not result.get("ok"):
        return _emit_errors(result)
    _print_build(result, as_json=args.json)
    return 0


def _runner(config: McpConfig) -> Any | None:
    try:
        from ontographia.mcp.execute import runner_from_config
    except ImportError as exc:
        print(
            'otg: Neo4j driver is not installed. Install with: pip install "ontographia[cli]"',
            file=sys.stderr,
        )
        print(f"otg: {exc}", file=sys.stderr)
        return None
    return runner_from_config(config)


def _run_execute(args: argparse.Namespace, config: McpConfig) -> int:
    ontology = _checked_ontology(config)
    if ontology is None:
        return 2
    try:
        intent = load_intent(args.intent)
    except ValueError as exc:
        print(f"otg: {exc}", file=sys.stderr)
        return 2
    try:
        engine = _engine(ontology)
    except Exception as exc:
        print(f"otg: failed to load ontology: {exc}", file=sys.stderr)
        return 1

    runner = None
    if config.neo4j_configured:
        try:
            runner = _runner(config)
        except Exception as exc:
            print(f"otg: failed to open Neo4j driver: {exc}", file=sys.stderr)
            return 1
        if runner is None:
            return 2
    try:
        result = execute_read_only(
            build_cypher=lambda bounded, dialect=None: build_read_only(
                engine,
                bounded,
                dialect=dialect or config.dialect,
            ),
            runner=runner,
            intent=intent,
            dialect=config.dialect,
            database=config.neo4j_database,
            row_limit=config.row_limit,
            configured_limit=config.row_limit,
        )
    finally:
        if runner is not None:
            runner.close()

    if not result.get("ok"):
        return _emit_errors(result)
    _print_execute(result, as_json=args.json)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = resolve_config(args)
    except Exception as exc:
        print(f"otg: configuration error: {exc}", file=sys.stderr)
        return 2
    if args.command == "build":
        return _run_build(args, config)
    if args.command == "execute":
        return _run_execute(args, config)
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
