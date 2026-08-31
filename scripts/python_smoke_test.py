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

    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
