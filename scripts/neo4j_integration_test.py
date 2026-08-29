#!/usr/bin/env python3
"""Neo4j integration test: mock LLM Intent -> Ontographia Cypher 25 -> execute.

Simulates the agent pipeline without calling an LLM:
  ontology schema -> (mock) Intent JSON -> Engine.build() -> Neo4j driver

For a real LLM locally, use examples/run_llm_e2e.py instead (not run in CI).

Usage:
  uv sync --group dev && uv run maturin develop --release
  ./scripts/start_neo4j.sh --seed
  python scripts/neo4j_integration_test.py

Environment:
  NEO4J_URI        default: bolt://localhost:7687
  NEO4J_USER       default: neo4j
  NEO4J_PASSWORD   default: ontographia
  NEO4J_LOAD_SEED  default: 1 (load examples/neo4j/seed.cypher before tests)
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
DEFAULT_ONTOLOGY = EXAMPLES / "manufacturing.native.yaml"
SEED_FILE = EXAMPLES / "neo4j/seed.cypher"

sys.path.insert(0, str(EXAMPLES))

from llm.extractors import MockIntentExtractor  # noqa: E402


@dataclass
class Neo4jConfig:
    uri: str
    user: str
    password: str
    load_seed: bool


@dataclass
class IntegrationCase:
    name: str
    user_question: str
    expected_rows: list[dict[str, Any]]


CASES = [
    IntegrationCase(
        name="bom_suppliers",
        user_question="List suppliers for parts in product SKU SPX-100",
        expected_rows=[
            {"supplier_name": "FormTech"},
            {"supplier_name": "MikroMotors"},
        ],
    ),
    IntegrationCase(
        name="quarantine_defects",
        user_question="Which defect codes affect quarantined lots?",
        expected_rows=[{"defect_code": "SURFACE_SCRATCH"}],
    ),
    IntegrationCase(
        name="line_plant",
        user_question="Which plant hosts production Line-1?",
        expected_rows=[{"plant_name": "Nagoya Plant"}],
    ),
]


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
    statements = parse_cypher25_seed(path)
    with driver.session() as session:
        for statement in statements:
            session.run(statement)


def run_case(engine: Any, driver: Any, case: IntegrationCase, extractor: MockIntentExtractor) -> None:
    schema = engine.intent_json_schema()
    intent = extractor.extract(case.user_question, schema)
    built = engine.build(intent, dialect="cypher25")

    if not built["query"].startswith("CYPHER 25"):
        raise AssertionError(f"{case.name}: expected CYPHER 25 query, got {built['query']!r}")

    with driver.session() as session:
        rows = session.run(built["query"], built["params"]).data()

    normalized = sorted(rows, key=lambda row: tuple(sorted(row.items())))
    expected = sorted(case.expected_rows, key=lambda row: tuple(sorted(row.items())))
    if normalized != expected:
        raise AssertionError(
            f"{case.name}: unexpected rows\n"
            f"  query : {built['query']}\n"
            f"  params: {built['params']}\n"
            f"  got   : {rows}\n"
            f"  want  : {case.expected_rows}"
        )

    print(f"ok  {case.name}")


def config_from_env() -> Neo4jConfig:
    return Neo4jConfig(
        uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        user=os.environ.get("NEO4J_USER", "neo4j"),
        password=os.environ.get("NEO4J_PASSWORD", "ontographia"),
        load_seed=os.environ.get("NEO4J_LOAD_SEED", "1") not in {"0", "false", "no"},
    )


def main() -> int:
    try:
        import ontographia
        from neo4j import GraphDatabase
    except ImportError:
        print(
            "requires ontographia and neo4j packages:\n"
            "  uv sync --group dev && uv run maturin develop --release",
            file=sys.stderr,
        )
        return 1

    cfg = config_from_env()
    if not DEFAULT_ONTOLOGY.is_file():
        print(f"ontology not found: {DEFAULT_ONTOLOGY}", file=sys.stderr)
        return 1

    try:
        driver = GraphDatabase.driver(cfg.uri, auth=(cfg.user, cfg.password))
        driver.verify_connectivity()
    except Exception as exc:  # noqa: BLE001 - surface driver errors to the user
        print(
            f"cannot connect to Neo4j at {cfg.uri}: {exc}\n"
            "Start and seed with: ./scripts/start_neo4j.sh --seed",
            file=sys.stderr,
        )
        return 1

    if cfg.load_seed:
        if not SEED_FILE.is_file():
            print(f"seed file not found: {SEED_FILE}", file=sys.stderr)
            return 1
        print(f"loading seed from {SEED_FILE.relative_to(ROOT)}")
        load_seed(driver, SEED_FILE)

    engine = ontographia.Engine.load(str(DEFAULT_ONTOLOGY))
    extractor = MockIntentExtractor()
    print(f"running {len(CASES)} integration case(s) against {cfg.uri}")
    try:
        for case in CASES:
            run_case(engine, driver, case, extractor)
    finally:
        driver.close()

    print("neo4j integration: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
