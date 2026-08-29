//! Emit Neo4j schema artifacts from an ontology file.
//!
//! ```bash
//! cargo run -p ontographia-schema --example emit_constraints -- examples/manufacturing.native.yaml
//! cargo run -p ontographia-schema --example emit_constraints -- examples/manufacturing.native.yaml \
//!   --out examples/neo4j/constraints.cypher --json-out examples/neo4j/schema.json
//! cargo run -p ontographia-schema --example emit_constraints -- examples/manufacturing.native.yaml \
//!   --snapshot examples/neo4j/catalog.snapshot.json
//! ```

use std::env;
use std::fs;
use std::path::PathBuf;
use std::process;

use ontographia_adapters::load_ontology_from_path;
use ontographia_schema::{
    diff, diff_has_errors, emit_cypher25_constraints, emit_schema_json, GraphSchema, GraphSnapshot,
};

struct CliArgs {
    ontology_path: PathBuf,
    out: Option<PathBuf>,
    json_out: Option<PathBuf>,
    snapshot: Option<PathBuf>,
}

fn main() {
    let cli = parse_args();

    let ontology = load_ontology_from_path(&cli.ontology_path).unwrap_or_else(|e| {
        eprintln!("failed to load ontology: {e}");
        process::exit(1);
    });

    let schema = GraphSchema::from_com(&ontology);
    let cypher = emit_cypher25_constraints(&schema);
    let json = emit_schema_json(&schema).unwrap_or_else(|e| {
        eprintln!("failed to serialize schema JSON: {e}");
        process::exit(1);
    });

    match &cli.out {
        Some(path) => write_file(path, &cypher, "constraints Cypher"),
        None => println!("{cypher}"),
    }

    match &cli.json_out {
        Some(path) => write_file(path, &json, "schema JSON"),
        None if cli.out.is_none() => eprintln!("(pass --json-out to write schema.json)"),
        None => {}
    }

    if let Some(path) = cli.snapshot {
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

fn write_file(path: &PathBuf, contents: &str, label: &str) {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).unwrap_or_else(|e| {
            eprintln!("failed to create directory {}: {e}", parent.display());
            process::exit(1);
        });
    }
    fs::write(path, contents).unwrap_or_else(|e| {
        eprintln!("failed to write {label} to {}: {e}", path.display());
        process::exit(1);
    });
    eprintln!("wrote {label}: {}", path.display());
}

fn parse_args() -> CliArgs {
    let mut args = env::args().skip(1);
    let ontology_path = args.next().map(PathBuf::from).unwrap_or_else(|| {
        eprintln!(
            "Usage: emit_constraints <ontology-path> [--out <constraints.cypher>] [--json-out <schema.json>] [--snapshot <catalog.json>]"
        );
        process::exit(1);
    });

    let mut out = None;
    let mut json_out = None;
    let mut snapshot = None;
    let rest: Vec<String> = args.collect();
    let mut i = 0;
    while i < rest.len() {
        match rest[i].as_str() {
            "--out" => {
                i += 1;
                out = rest.get(i).map(PathBuf::from);
            }
            "--json-out" => {
                i += 1;
                json_out = rest.get(i).map(PathBuf::from);
            }
            "--snapshot" => {
                i += 1;
                snapshot = rest.get(i).map(PathBuf::from);
            }
            flag => {
                eprintln!("unknown flag: {flag}");
                process::exit(1);
            }
        }
        i += 1;
    }

    CliArgs {
        ontology_path,
        out,
        json_out,
        snapshot,
    }
}
