#!/usr/bin/env python3
"""Smoke test for the Python bindings (CI and local use after `uv sync`)."""

from __future__ import annotations

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
    result = engine.build(
        {
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
    )

    if not result["query"].startswith("CYPHER 25"):
        print(f"unexpected query prefix: {result['query']!r}", file=sys.stderr)
        return 1

    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
