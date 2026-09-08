# Track B baseline — Text2Cypher schema → Ontographia

- Recorded: `2026-09-03T11:29:09Z`
- Git: `9b3c7cf`
- Dataset: `neo4j/text2cypher-2025v1` split `test`
- Filter: demo `database_reference_alias` + `Node properties` schema
- Limit per ref: 15

## Summary

| metric | value |
|--------|------:|
| demo DBs (refs) | 15 |
| questions scored | 211 |
| convert OK | 15 |
| convert fail | 0 |
| Engine.load OK | 15 |
| Engine.load fail | 0 |
| mean label coverage (gold Cypher ∩ ontology) | 0.9586 |
| mean relationship coverage | 1.0 |
| mean property coverage | 0.8132 |

## Per database

| ref | classes | rels | props | load |
|-----|--------:|-----:|------:|------|
| `neo4jlabs_demo_db_bluesky` | 1 | 1 | 7 | ok |
| `neo4jlabs_demo_db_buzzoverflow` | 3 | 2 | 16 | ok |
| `neo4jlabs_demo_db_eoflix` | 13 | 27 | 76 | ok |
| `neo4jlabs_demo_db_fincen` | 3 | 5 | 32 | ok |
| `neo4jlabs_demo_db_gameofthrones` | 1 | 5 | 10 | ok |
| `neo4jlabs_demo_db_grandstack` | 4 | 3 | 13 | ok |
| `neo4jlabs_demo_db_movies` | 2 | 6 | 6 | ok |
| `neo4jlabs_demo_db_network` | 17 | 42 | 41 | ok |
| `neo4jlabs_demo_db_northwind` | 5 | 4 | 51 | ok |
| `neo4jlabs_demo_db_offshoreleaks` | 5 | 26 | 75 | ok |
| `neo4jlabs_demo_db_openstreetmap` | 10 | 33 | 0 | ok |
| `neo4jlabs_demo_db_recommendations` | 6 | 8 | 46 | ok |
| `neo4jlabs_demo_db_stackoverflow2` | 5 | 6 | 0 | ok |
| `neo4jlabs_demo_db_twitch` | 5 | 13 | 13 | ok |
| `neo4jlabs_demo_db_twitter` | 6 | 18 | 0 | ok |

## Interpretation

This measures **schema conversion external validity**, not Intent generation quality.
Coverage asks whether labels/rels/properties appearing in gold Cypher exist in the
converted ontology. Gaps usually mean missing relationship patterns in the schema text,
or Cypher using tokens the heuristic extractor mis-parses.

Regenerate:

```bash
uv run --with datasets python examples/llm/eval/run_track_b.py --record
```
