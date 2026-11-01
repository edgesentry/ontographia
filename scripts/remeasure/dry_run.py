#!/usr/bin/env python3
"""Offline remeasure dry-run: check fixture Intent JSON against expected Cypher.

No engine, LLM, network, or Neo4j. This offline scaffold (#138) verifies that a
saved expected Cypher still agrees with its Intent fixture. A future full
remeasure can replace the consistency checks with a real `Engine.build`
comparison.

Usage:
  python3 scripts/remeasure/dry_run.py
  python3 scripts/remeasure/dry_run.py --fixtures scripts/remeasure/fixtures
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_FIXTURES = HERE / "fixtures"
INTENT_SUFFIX = ".intent.json"
CYPHER_SUFFIX = ".expected.cypher"

TOP_LEVEL_KEYS = {
    "start",
    "traverse",
    "filter",
    "return",
    "order_by",
    "limit",
    "skip",
    "optional",
}
OP_SYMBOLS = {
    "eq": "=",
    "neq": "<>",
    "lt": "<",
    "lte": "<=",
    "gt": ">",
    "gte": ">=",
    "in": "IN",
    "contains": "CONTAINS",
}
DIRECTION_TOKENS = {
    "out": "-[:{rel}]->",
    "in": "<-[:{rel}]-",
    "both": "-[:{rel}]-",
}


def expected_path_for(intent_path: Path) -> Path:
    stem = intent_path.name.removesuffix(INTENT_SUFFIX)
    return intent_path.with_name(stem + CYPHER_SUFFIX)


def check_node(
    errors: list[str], node: Any, cypher: str, where: str
) -> tuple[str, str] | None:
    if not isinstance(node, dict):
        errors.append(f"{where}: expected an object")
        return None
    alias, cls = node.get("alias"), node.get("class")
    if not isinstance(alias, str) or not isinstance(cls, str):
        errors.append(f"{where}: expected string 'alias' and 'class'")
        return None
    if f"({alias}:{cls})" not in cypher:
        errors.append(f"{where}: expected node pattern ({alias}:{cls}) in Cypher")
    return alias, cls


def check_case(intent_path: Path, cypher_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        intent = json.loads(intent_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{intent_path}: cannot load Intent JSON: {exc}"]
    if not isinstance(intent, dict):
        return [f"{intent_path}: Intent must be a JSON object"]

    unknown = sorted(set(intent) - TOP_LEVEL_KEYS)
    if unknown:
        errors.append(f"{intent_path}: unknown Intent keys: {', '.join(unknown)}")
    for key in ("start", "return"):
        if key not in intent:
            errors.append(f"{intent_path}: missing required key '{key}'")

    try:
        cypher = cypher_path.read_text(encoding="utf-8")
    except OSError as exc:
        return errors + [f"{cypher_path}: cannot read expected Cypher: {exc}"]

    lines = [line.strip() for line in cypher.splitlines() if line.strip()]
    if not lines or lines[0].upper() != "CYPHER 25":
        errors.append(f"{cypher_path}: expected a leading 'CYPHER 25' line")

    start = intent.get("start")
    if start is not None:
        check_node(errors, start, cypher, f"{intent_path}: start")

    for index, step in enumerate(intent.get("traverse", []) or []):
        where = f"{intent_path}: traverse[{index}]"
        if not isinstance(step, dict):
            errors.append(f"{where}: expected an object")
            continue
        rel, direction = step.get("relationship"), step.get("direction")
        if (
            not isinstance(rel, str)
            or not isinstance(direction, str)
            or direction not in DIRECTION_TOKENS
        ):
            errors.append(f"{where}: expected 'relationship' and a valid 'direction'")
        else:
            token = DIRECTION_TOKENS[direction].format(rel=rel)
            if token not in cypher:
                errors.append(f"{where}: expected traversal token {token!r} in Cypher")
        check_node(errors, step.get("to"), cypher, f"{where}.to")

    for index, filt in enumerate(intent.get("filter", []) or []):
        where = f"{intent_path}: filter[{index}]"
        if not isinstance(filt, dict):
            errors.append(f"{where}: expected an object")
            continue
        alias, prop, op = filt.get("alias"), filt.get("property"), filt.get("op")
        symbol = OP_SYMBOLS.get(op) if isinstance(op, str) else None
        if not isinstance(alias, str) or not isinstance(prop, str) or symbol is None:
            errors.append(f"{where}: expected 'alias', 'property', and a valid 'op'")
            continue
        expected = f"{alias}.{prop} {symbol} $param_{index}"
        if expected not in cypher:
            errors.append(f"{where}: expected {expected!r} in Cypher")

    return_clauses = [
        line for line in lines if line.upper().startswith("RETURN ")
    ]
    for index, item in enumerate(intent.get("return", []) or []):
        where = f"{intent_path}: return[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{where}: expected an object")
            continue
        alias, prop = item.get("alias"), item.get("property")
        if not isinstance(alias, str):
            errors.append(f"{where}: expected string 'alias'")
            continue
        expr = f"{alias}.{prop}" if isinstance(prop, str) else alias
        target = f"{expr} AS {item['as_name']}" if item.get("as_name") else expr
        if not any(target in clause for clause in return_clauses):
            errors.append(f"{where}: expected {target!r} in a RETURN clause")

    limit = intent.get("limit")
    if limit is not None and f"LIMIT {limit}" not in cypher:
        errors.append(f"{intent_path}: expected 'LIMIT {limit}' in Cypher")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=DEFAULT_FIXTURES,
        help=f"fixture directory (default: {DEFAULT_FIXTURES})",
    )
    args = parser.parse_args()

    intent_paths = sorted(args.fixtures.glob(f"*{INTENT_SUFFIX}"))
    if not intent_paths:
        print(f"no *{INTENT_SUFFIX} fixtures under {args.fixtures}", file=sys.stderr)
        return 1

    failed = 0
    for intent_path in intent_paths:
        cypher_path = expected_path_for(intent_path)
        errors = check_case(intent_path, cypher_path)
        if errors:
            failed += 1
            for error in errors:
                print(f"FAIL {error}", file=sys.stderr)
            continue
        print(f"ok: {intent_path.name} -> {cypher_path.name}")
        if len(intent_paths) == 1:
            print("--- expected Cypher ---")
            print(cypher_path.read_text(encoding="utf-8").rstrip())

    print(f"{len(intent_paths) - failed}/{len(intent_paths)} fixtures passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
