use std::fs;
use std::path::PathBuf;

use clap::Args;
use ontographia_adapters::load_ontology_from_path;
use ontographia_schema::{
    diff, diff_has_errors, emit_cypher25_constraints, emit_schema_json, GraphSchema, GraphSnapshot,
};

#[derive(Args)]
pub struct SchemaArgs {
    /// Path to the ontology file
    pub ontology: PathBuf,

    /// Write UNIQUE constraint Cypher to this file (default: stdout)
    #[arg(long)]
    pub out: Option<PathBuf>,

    /// Write schema.json to this file
    #[arg(long)]
    pub json_out: Option<PathBuf>,

    /// Compare against a catalog snapshot JSON; exit 1 on drift
    #[arg(long)]
    pub snapshot: Option<PathBuf>,
}

pub fn run(args: SchemaArgs) -> Result<(), Box<dyn std::error::Error>> {
    let ontology = load_ontology_from_path(&args.ontology)?;
    let schema = GraphSchema::from_com(&ontology);
    let cypher = emit_cypher25_constraints(&schema);
    let json = emit_schema_json(&schema)?;

    match &args.out {
        Some(path) => write_file(path, &cypher, "constraints Cypher")?,
        None => println!("{cypher}"),
    }

    if let Some(path) = &args.json_out {
        write_file(path, &json, "schema JSON")?;
    }

    if let Some(path) = args.snapshot {
        let text = fs::read_to_string(&path)?;
        let snapshot = GraphSnapshot::from_json_str(&text)?;
        let result = diff(&schema, &snapshot);
        if diff_has_errors(&result) {
            return Err(format!("schema diff errors: {result:?}").into());
        }
        eprintln!("snapshot matches ontology-derived schema: {}", path.display());
    }

    Ok(())
}

fn write_file(path: &PathBuf, contents: &str, label: &str) -> Result<(), Box<dyn std::error::Error>> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(path, contents)?;
    eprintln!("wrote {label}: {}", path.display());
    Ok(())
}
