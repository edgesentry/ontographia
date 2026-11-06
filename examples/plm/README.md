# Thin PLM COM (demo subset)

[`plm.native.yaml`](plm.native.yaml) is a small Ontographia native ontology for the `edgesentry/ontographia-plm-demo` project (Addresses #153).

> **Subset disclaimer:** this is a **subset inspired by** the sources below. It is **not** a normative Catena-X, ISA-95, or IOF profile. It exists for demos and Intent enum binding only.

## Contents

- Classes: `Item`, `Part`, `Assembly`, `Revision`, `ECO`, `Operation`, `WorkCenter`, `Substance`, `Customer`
  - `Item` is a thin shared superclass of `Part`, `Assembly`, `Revision`, and `Substance`, so polymorphic relationships can be declared once.
- Relationships: `CONTAINS`, `CONSUMES`, `AFFECTS`, `ALTERNATE_OF`, `PERFORMED_AT`, `PRODUCES`, `HAS_REVISION`, `ORDERED_BY`
- Properties are kept minimal (e.g. `part_number`, `revision_id`, `eco_id`, `cas_number`).

## Sources of inspiration

- Catena-X BOM: <https://raw.githubusercontent.com/big-data-spaces/ontology/main/ontology/bill-of-material_ontology.ttl>
- DTC Manufacturing Ontologies (ISA-95 operations definition): <https://github.com/digitaltwinconsortium/ManufacturingOntologies/tree/main/Ontologies/ISA95/CommonObjectModels/Part2/OperationsDefinition>
- IOF Core: <https://spec.industrialontologies.org/portal/release/202502/core/CoreOntology.html>

## How `ontographia-plm-demo` consumes this

Point the demo at this file path (`examples/plm/plm.native.yaml` in this repository) and load it with the `otg` CLI or the Rust `Engine` (via `ontographia_adapters::load_ontology_from_path`). Class and relationship names above are the values bound into Intent enums.

```bash
cargo run -p ontographia-cli --bin otg -- schema examples/plm/plm.native.yaml
```

See [docs/otg.md](../../docs/otg.md) and [docs/rust.md](../../docs/rust.md).
