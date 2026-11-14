#!/usr/bin/env python3
"""Smoke test for the Python bindings (CI and local use after `uv sync`)."""

from __future__ import annotations

import json
import sys


def main() -> int:
    try:
        import ontographia
    except ImportError:
        print(
            "ontographia is not installed. Set up with:\n"
            "  uv sync --group dev && uv run maturin develop --release",
            file=sys.stderr,
        )
        return 1

    engine = ontographia.Engine.load("examples/manufacturing.native.yaml")
    with open("examples/sample_intent.json") as f:
        intent = json.load(f)
    result = engine.build(intent)

    if not result["query"].startswith("CYPHER 25"):
        print(f"unexpected query prefix: {result['query']!r}", file=sys.stderr)
        return 1

    # Issue #81: unknown Intent keys must be rejected, not silently ignored.
    bad_intent = dict(intent)
    bad_intent["filters"] = bad_intent.pop("filter")
    if not _raises_value_error(engine.build, bad_intent, "unknown field `filters`"):
        return 1

    # Issue #81: unknown dialect must raise, not fall back to cypher25.
    if not _raises_value_error(
        lambda i: engine.build(i, dialect="cyhper5"), intent, "unknown dialect 'cyhper5'"
    ):
        return 1
    if not engine.build(intent, dialect="cypher5")["query"].startswith("CYPHER 5"):
        print("cypher5 dialect not honoured", file=sys.stderr)
        return 1

    schema = engine.intent_json_schema()
    if schema.get("additionalProperties") is not False:
        print("Intent JSON Schema must set additionalProperties: false", file=sys.stderr)
        return 1
    if "not_exists" not in schema.get("properties", {}):
        print("Intent JSON Schema must include not_exists", file=sys.stderr)
        return 1

    # Correlated NOT EXISTS sub-pattern: emitted and parameter-bound.
    not_exists_engine = ontographia.Engine.load("examples/part_usage.native.yaml")
    with open("examples/part_usage_not_exists.json") as f:
        not_exists_intent = json.load(f)
    not_exists_result = not_exists_engine.build(not_exists_intent)
    if "NOT EXISTS { MATCH" not in not_exists_result["query"]:
        print(
            f"not_exists query missing subquery: {not_exists_result['query']!r}",
            file=sys.stderr,
        )
        return 1
    if not_exists_result["params"] != {
        "param_0": "fasteners-and-hardware",
        "param_1": "exact",
    }:
        print(
            f"unexpected not_exists params: {not_exists_result['params']!r}",
            file=sys.stderr,
        )
        return 1

    print("ok")
    return 0


def _raises_value_error(fn, arg, expected: str) -> bool:
    try:
        fn(arg)
    except ValueError as exc:
        if expected not in str(exc):
            print(f"expected {expected!r} in error, got {exc!r}", file=sys.stderr)
            return False
        return True
    print(f"expected ValueError containing {expected!r}", file=sys.stderr)
    return False


if __name__ == "__main__":
    raise SystemExit(main())
