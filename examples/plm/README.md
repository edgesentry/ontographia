# Thin PLM COM + desk-fan EOL fixture (demo subset)

[`plm.native.yaml`](plm.native.yaml) is a small Ontographia native ontology for the `edgesentry/ontographia-plm-demo` project (Addresses #153 and #154). The fixture, fixed Intents, and chips in this directory use **fiction only**.

> **Subset disclaimer:** this is a **subset inspired by** the sources below. It is **not** a normative Catena-X, ISA-95, or IOF profile. It exists for demos and Intent enum binding only.

## Scenario choice

Issue #154 is titled “PFAS/EOL fixtures”, but the scenario was locked on 2026-11-06 to **desk-fan bracket EOL/ECO**, not PFAS. The fixture therefore has no `Substance` nodes, no CAS numbers, and no real customer names. The COM still keeps `Substance` so a PFAS variant can be added later without changing the Intent enums. All part numbers, SKUs, customers, and ECO ids in the fixture are fictional.

## Files

| File | Purpose |
|------|---------|
| [`plm.native.yaml`](plm.native.yaml) | Thin PLM COM (unchanged from #156) |
| [`fixtures/deskfan_eol.graph.json`](fixtures/deskfan_eol.graph.json) | 18-node embedded graph, lane-tagged `ebom` / `bop` / `sbom` |
| [`intents/`](intents/) | Five fixed Intents, one per chip question |
| [`chips.json`](chips.json) | Five UI chips (Japanese + English labels), 1:1 with the Intent files |

## Fixture

`fixtures/deskfan_eol.graph.json` contains `nodes[{id, labels, properties}]` and `edges[{from, to, type, properties?}]`. Node ids are unique, `part_number` values are unique across `Part` and `Assembly` nodes, and `revision_id` / `eco_id` values are unique where the COM requires them.

Lane tags group the graph for the demo UI:

- **`ebom`** — `DEMO-BRKT-01`, `DEMO-BRKT-02`, the three `DEMO-FAN-*` assemblies, the three revisions, and the two ECOs.
- **`bop`** — `OP-BRKT-MOUNT`, `OP-BRKT-ALT`, `OP-FAN-ASSY`, `WC-LINE-A`, `WC-LINE-B`.
- **`sbom`** — three fictional customers (`CUST-EU-01`, `CUST-NA-01`, `CUST-APAC-01`).

## Ripple path

`DEMO-BRKT-01` is the EOL mount bracket. In the EBOM it sits directly under `DEMO-FAN-100`, `DEMO-FAN-200`, and `DEMO-FAN-300`; the 100 mm assembly also has revision `REV-FAN-100-A`, and each assembly has a fictional shipping destination in the S-BOM. In the BOP, `OP-BRKT-MOUNT` **CONSUMES** `DEMO-BRKT-01` and is **PERFORMED_AT** `WC-LINE-A`; `OP-FAN-ASSY` **PRODUCES** `DEMO-FAN-100` at the same line. The open ECO `DEMO-ECO-FAN-01` **AFFECTS** the bracket and all three assemblies. `DEMO-BRKT-02` is the **ALTERNATE_OF** `DEMO-BRKT-01`; it has its own revision, and `OP-BRKT-ALT` consumes it at `WC-LINE-B`. The closed ECO `DEMO-ECO-FAN-02` only affects the alternate. So an EOL decision on `DEMO-BRKT-01` ripples to three SKUs, one work center, three customers, and one open ECO, while the alternate route is already represented in the same fixture.

## Fixed questions

Each chip in [`chips.json`](chips.json) carries the stable `chip_id`, `intent_path`, and `lane_hints` used by the demo, plus a bilingual label/description pair: `label_ja` / `description_ja` and `label_en` / `description_en`. Both languages express the same question, so UI code can pick a label by locale without changing the bound Intent.

| Chip | `label_en` | `label_ja` | `description_en` | Intent | Lanes |
|------|------------|------------|------------------|--------|-------|
| `affected_products` | Which products are affected? | 影響を受ける製品は？ | Return desk-fan assemblies that directly contain DEMO-BRKT-01 | [`intents/01_affected_products.json`](intents/01_affected_products.json) | `ebom` |
| `affected_bop` | Which manufacturing operations and work centers are affected? | 影響を受ける製造工程・設備は？ | Return work centers that perform OP-BRKT-MOUNT (operation-start due to current core reverse-direction limits) | [`intents/02_affected_bop.json`](intents/02_affected_bop.json) | `bop` |
| `affected_customers` | Which customers are affected? | 影響を受ける顧客は？ | Return customers of assemblies that contain DEMO-BRKT-01 | [`intents/03_affected_customers.json`](intents/03_affected_customers.json) | `ebom`, `sbom` |
| `alternatives` | What are the alternate parts? | 代替部品は？ | Return alternate part DEMO-BRKT-02 for DEMO-BRKT-01 | [`intents/04_alternatives.json`](intents/04_alternatives.json) | `ebom` |
| `residual_risk` | What residual risk remains after the change? | 変更後の残存リスクは？ | Return Items affected by open DEMO-ECO-FAN-01 | [`intents/05_residual_risk.json`](intents/05_residual_risk.json) | `ebom`, `bop`, `sbom` |

The filters are already bound to fixture values (`DEMO-BRKT-01`, `OP-BRKT-MOUNT`, `DEMO-ECO-FAN-01`, `status = open`), so a chip maps directly to a deterministic Intent without an LLM. Adding or refining wording only touches this catalogue; it never changes the generated Cypher.

## Intent compatibility note

The literal BOP shape is `Part --IN CONSUMES--> Operation --OUT PERFORMED_AT--> WorkCenter`. The current core validator rejects that first hop with `relationship 'CONSUMES' does not originate from class 'Part'` because it checks `from_class` without considering `direction: "in"` (`crates/ontographia-core/src/validate.rs`). Core crates and `plm.native.yaml` are out of scope for #154, so `02_affected_bop.json` starts at `Operation` and filters the known operation name `OP-BRKT-MOUNT`; the fixture still contains the `OP-BRKT-MOUNT -CONSUMES-> DEMO-BRKT-01` edge, so the Part → Operation → WorkCenter path remains traceable in the data. A direction-aware validation change is a separate core follow-up; this directory does not work around it by weakening the COM.

## Verify

```bash
otg schema examples/plm/plm.native.yaml

for f in examples/plm/intents/*.json; do
  otg build --ontology examples/plm/plm.native.yaml --intent "$f"
done

jq '.nodes | length' examples/plm/fixtures/deskfan_eol.graph.json
jq '[.nodes[].id] | length == (unique | length)' examples/plm/fixtures/deskfan_eol.graph.json
jq '[.nodes[] | select(.labels[] == "Part" or .labels[] == "Assembly") | .properties.part_number] | length == (unique | length)' examples/plm/fixtures/deskfan_eol.graph.json
jq '[.edges[].type] | unique' examples/plm/fixtures/deskfan_eol.graph.json
```

`otg schema` exits 0 and emits the `Part`, `Assembly`, `Revision`, `ECO`, and `Substance` constraints. Every Intent exits 0 and prints Cypher 25 plus a `params` line.

## How `ontographia-plm-demo` consumes this

Point the demo at `examples/plm/plm.native.yaml` in this repository and load it with the `otg` CLI or the Rust `Engine` (via `ontographia_adapters::load_ontology_from_path`). Load `examples/plm/chips.json` for the five fixed questions, render `label_en` or `label_ja` according to the UI locale, read each `intent_path`, and pass that Intent to `otg build` or the `Engine`. The fixture JSON is app-side seed data; it can be loaded into Neo4j or rendered as an in-memory graph, and its `lane` properties are the UI grouping hints. Class and relationship names in the COM are the values bound into Intent enums.

```bash
cargo run -p ontographia-cli --bin otg -- schema examples/plm/plm.native.yaml
cargo run -p ontographia-cli --bin otg -- build \
  --ontology examples/plm/plm.native.yaml \
  --intent examples/plm/intents/01_affected_products.json
```

## Sources of inspiration

- Catena-X BOM: <https://raw.githubusercontent.com/big-data-spaces/ontology/main/ontology/bill-of-material_ontology.ttl>
- DTC Manufacturing Ontologies (ISA-95 operations definition): <https://github.com/digitaltwinconsortium/ManufacturingOntologies/tree/main/Ontologies/ISA95/CommonObjectModels/Part2/OperationsDefinition>
- IOF Core: <https://spec.industrialontologies.org/portal/release/202502/core/CoreOntology.html>

See [docs/otg.md](../../docs/otg.md) and [docs/rust.md](../../docs/rust.md).
