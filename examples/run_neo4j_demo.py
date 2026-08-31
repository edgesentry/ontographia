#!/usr/bin/env python3
"""Generate a Cypher 25 query with Ontographia and optionally execute it against Neo4j.

Manufacturing demo intent:
  List supplier names for parts in product SKU SPX-100 (BOM + supply chain).

Usage:
  python examples/run_neo4j_demo.py --ontology examples/manufacturing.native.yaml
  python examples/run_neo4j_demo.py --ontology examples/manufacturing.owl.ttl --execute --password <pw>
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Supply-chain query: Product -> Part -> Supplier, filtered by SKU
DEMO_INTENT = {
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
    "filter": [{"alias": "product", "property": "sku", "op": "eq", "value": "SPX-100"}],
    "return": [{"alias": "supplier", "property": "name", "as_name": "supplier_name"}],
    "limit": 20,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Ontographia manufacturing Neo4j demo")
    parser.add_argument(
        "--ontology",
        default="examples/manufacturing.native.yaml",
        help="Ontology file (any supported format)",
    )
    parser.add_argument("--dialect", default="cypher25", choices=["cypher25", "cypher5", "gql"])
    parser.add_argument("--uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--user", default=os.environ.get("NEO4J_USER", "neo4j"))
    parser.add_argument("--password", default=os.environ.get("NEO4J_PASSWORD"))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    try:
        import ontographia
    except ImportError:
        print(
            "ontographia is not installed. Install with:\n"
            "  pip install ontographia",
            file=sys.stderr,
        )
        return 1

    engine = ontographia.Engine.load(args.ontology)
    result = engine.build(DEMO_INTENT, dialect=args.dialect)

    print("=== Generated query ===")
    print(result["query"])
    print("\n=== Parameters ===")
    print(json.dumps(result["params"], ensure_ascii=False, indent=2))

    if not args.execute:
        print("\n(dry-run: pass --execute to run against Neo4j after seed.cypher)")
        return 0

    if not args.password:
        print("NEO4J_PASSWORD or --password is required for --execute", file=sys.stderr)
        return 1

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("neo4j is required for --execute. Install with:\n  pip install neo4j", file=sys.stderr)
        return 1

    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    with driver.session() as session:
        records = session.run(result["query"], result["params"]).data()
    driver.close()

    print("\n=== Query result ===")
    print(json.dumps(records, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
