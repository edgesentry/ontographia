# Remeasure dry-run scaffold

Offline scaffold for the Part 3 remeasure follow-up ([#138](https://github.com/edgesentry/ontographia/issues/138)).
It loads a fixture Intent JSON and checks the saved expected Cypher is still
consistent with it. **No LLM, API key, network, or Neo4j.**

## Run

```bash
python3 scripts/remeasure/dry_run.py
```

The command prints the expected Cypher and exits `0` on a match. It exits
non-zero for a missing fixture pair, malformed Intent JSON, or a Cypher string
that disagrees with the Intent (start node, traversal, filter, return, limit).

Use another fixture directory with `--fixtures DIR`.

## Layout

```text
scripts/remeasure/
├── dry_run.py
├── README.md
└── fixtures/
    ├── suppliers_by_sku.intent.json
    └── suppliers_by_sku.expected.cypher
```

Every `*.intent.json` needs a sibling `*.expected.cypher` with the same stem.
The default run picks up all pairs under `fixtures/`.

## Provenance and scope

The fixture mirrors the successful no-LLM replay in
[`examples/e2e/v0.1.6-gemini/`](../../examples/e2e/v0.1.6-gemini/) (Ontographia
0.1.6, Cypher 25). This is a fixture consistency check, not an engine test.

Growing it into a full n=3/n=5 remeasure harness (LLM extraction, LiteLLM,
Neo4j execution, CI job) is later work and intentionally out of scope here.
