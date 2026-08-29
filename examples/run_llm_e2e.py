#!/usr/bin/env python3
"""Local-only E2E: natural language -> LLM Intent JSON -> Ontographia -> Neo4j.

Not run in CI. Use mock backend (default) for offline demos, or any
OpenAI-compatible endpoint for a real LLM.

Usage:
  # Offline (fixture LLM, no API key):
  uv run python examples/run_llm_e2e.py \\
    --question "List suppliers for parts in product SKU SPX-100" \\
    --execute --password ontographia

  # Real LLM (OpenAI-compatible):
  export ONTOGRAPHIA_LLM_BACKEND=openai
  export OPENAI_API_KEY=sk-...
  # LiteLLM proxy (OpenAI / Gemini / Cursor-style):
  #   ./scripts/litellm/start.sh
  #   ./scripts/litellm/run-e2e.sh openai "List suppliers for parts in product SKU SPX-100" --execute --password ontographia
  # See docs/litellm-local.md
  # Ollama example:
  # export OPENAI_BASE_URL=http://localhost:11434/v1
  # export OPENAI_MODEL=llama3.1
  uv run python examples/run_llm_e2e.py \\
    --question "Which plant hosts production Line-1?" \\
    --execute --password ontographia

Environment:
  ONTOGRAPHIA_LLM_BACKEND   mock (default) | openai
  OPENAI_API_KEY            required for openai backend
  OPENAI_BASE_URL           default https://api.openai.com/v1
  OPENAI_MODEL              default gpt-4o-mini
  NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
DEFAULT_ONTOLOGY = EXAMPLES / "manufacturing.native.yaml"
SEED_FILE = EXAMPLES / "neo4j/seed.cypher"

sys.path.insert(0, str(EXAMPLES))

from llm.extractors import create_extractor  # noqa: E402
from llm.pipeline import extract_validated_intent  # noqa: E402


def parse_cypher25_seed(path: Path) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("//") or not stripped:
            continue
        if stripped.upper() == "CYPHER 25":
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current).strip())
    return [block for block in blocks if block]


def load_seed(driver: Any, path: Path) -> None:
    with driver.session() as session:
        for statement in parse_cypher25_seed(path):
            session.run(statement)


def main() -> int:
    parser = argparse.ArgumentParser(description="Local LLM + Ontographia + Neo4j E2E")
    parser.add_argument(
        "--question",
        required=True,
        help="Natural-language graph question",
    )
    parser.add_argument(
        "--ontology",
        default=str(DEFAULT_ONTOLOGY),
        help="Ontology file (any supported format)",
    )
    parser.add_argument(
        "--backend",
        choices=["mock", "openai"],
        default=None,
        help="LLM backend (default: ONTOGRAPHIA_LLM_BACKEND or mock)",
    )
    parser.add_argument(
        "--no-json-schema",
        action="store_true",
        help="Skip json_schema response_format (for older local models)",
    )
    parser.add_argument("--dialect", default="cypher25", choices=["cypher25", "cypher5", "gql"])
    parser.add_argument("--uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--user", default=os.environ.get("NEO4J_USER", "neo4j"))
    parser.add_argument("--password", default=os.environ.get("NEO4J_PASSWORD"))
    parser.add_argument("--execute", action="store_true", help="Execute generated query against Neo4j")
    parser.add_argument(
        "--load-seed",
        action="store_true",
        help="Load examples/neo4j/seed.cypher before executing",
    )
    args = parser.parse_args()

    try:
        import ontographia
    except ImportError:
        print(
            "ontographia is not installed. Set up with:\n"
            "  uv sync --group dev && uv run maturin develop --release",
            file=sys.stderr,
        )
        return 1

    engine = ontographia.Engine.load(args.ontology)
    schema = engine.intent_json_schema()
    ontology = engine.ontology_json()

    try:
        extractor = create_extractor(
            args.backend,
            use_json_schema=not args.no_json_schema,
        )
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    backend_name = args.backend or os.environ.get("ONTOGRAPHIA_LLM_BACKEND", "mock")
    print(f"=== LLM backend: {backend_name} ===")
    print(f"=== Question ===\n{args.question}\n")

    try:
        intent, result = extract_validated_intent(
            engine,
            extractor,
            args.question,
            schema,
            ontology=ontology,
            dialect=args.dialect,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Intent extraction/validation failed: {exc}", file=sys.stderr)
        return 1

    print("=== Intent JSON ===")
    print(json.dumps(intent, ensure_ascii=False, indent=2))

    print("\n=== Generated query ===")
    print(result["query"])
    print("\n=== Parameters ===")
    print(json.dumps(result["params"], ensure_ascii=False, indent=2))

    if not args.execute:
        print("\n(dry-run: pass --execute to run against Neo4j)")
        return 0

    if not args.password:
        print("NEO4J_PASSWORD or --password is required for --execute", file=sys.stderr)
        return 1

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("neo4j is required for --execute (included in uv dev group)", file=sys.stderr)
        return 1

    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    try:
        driver.verify_connectivity()
        if args.load_seed:
            if not SEED_FILE.is_file():
                print(f"seed file not found: {SEED_FILE}", file=sys.stderr)
                return 1
            print(f"\nloading seed from {SEED_FILE.relative_to(ROOT)}")
            load_seed(driver, SEED_FILE)

        with driver.session() as session:
            rows = session.run(result["query"], result["params"]).data()
    except Exception as exc:  # noqa: BLE001
        print(f"Neo4j error: {exc}", file=sys.stderr)
        return 1
    finally:
        driver.close()

    print("\n=== Query result ===")
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
