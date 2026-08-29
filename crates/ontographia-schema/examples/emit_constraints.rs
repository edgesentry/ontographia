//! Emit Neo4j Cypher 25 constraint DDL from an ontology file.
//!
//! ```bash
//! cargo run -p ontographia-schema --example emit_constraints -- examples/manufacturing.native.yaml
//! cargo run -p ontographia-schema --example emit_constraints -- examples/manufacturing.native.yaml --snapshot examples/neo4j/catalog.snapshot.json
//! ```

use std::env;
use std::fs;
use std::path::PathBuf;
use std::process;

use ontographia_adapters::load_ontology_from_path;
use ontographia_schema::{diff, diff_has_errors, emit_cypher25_constraints, GraphSchema, GraphSnapshot};

fn main() {
    let mut args = env::args().skip(1);
    let ontology_path = args.next().unwrap_or_else(|| {
        eprintln!("Usage: emit_constraints <ontology-path> [--snapshot <catalog.json>]");
        process::exit(1);
    });

    let ontology = load_ontology_from_path(&ontology_path).unwrap_or_else(|e| {
        eprintln!("failed to load ontology: {e}");
        process::exit(1);
    });

    let schema = GraphSchema::from_com(&ontology);
    let cypher = emit_cypher25_constraints(&schema);
    println!("{cypher}");

    let snapshot_path = parse_snapshot_arg(args.collect());
    if let Some(path) = snapshot_path {
        let text = fs::read_to_string(&path).unwrap_or_else(|e| {
            eprintln!("failed to read snapshot {}: {e}", path.display());
            process::exit(1);
        });
        let snapshot = GraphSnapshot::from_json_str(&text).unwrap_or_else(|e| {
            eprintln!("invalid snapshot JSON: {e}");
            process::exit(1);
        });
        let result = diff(&schema, &snapshot);
        if diff_has_errors(&result) {
            eprintln!("schema diff errors: {result:?}");
            process::exit(1);
        }
        eprintln!("snapshot matches ontology-derived schema: {}", path.display());
    }
}

fn parse_snapshot_arg(args: Vec<String>) -> Option<PathBuf> {
    let mut iter = args.into_iter();
    while let Some(arg) = iter.next() {
        if arg == "--snapshot" {
            return iter.next().map(PathBuf::from);
        }
    }
    None
}
