# Track B Exec Match — spot evaluation

- Recorded: `2026-09-08T15:10:33Z`
- Git: `5965059`
- Model: `ontographia-gemini` → upstream **Gemini 3.7 Flash** (`gemini-3.7-flash`)
- Refs: neo4jlabs_demo_db_movies, neo4jlabs_demo_db_recommendations
- N: 60 (seed=53)
- URI: `neo4j+s://demo.neo4jlabs.com`

## Summary

- Compile OK: 41/60 (0.6833)
- Exec Match: 1 / 38 (rate=0.0263)
- Jaccard mean: 0.0263
- Structure F1 (label/rel/prop): 0.8229 / 0.6667 / 0.613

## Claim boundary

Spot external validity for Intent → deterministic Cypher on public demo DBs. No Intent Exact Match (HF gold is Cypher). Not a Text2Cypher SOTA claim; not comparable to Track A H1–H3 mechanical support.

```bash
uv run --with datasets --with neo4j python examples/llm/eval/run_track_b_exec.py --record
```
