use std::fs;
use std::io::{self, Read};
use std::path::PathBuf;

use clap::Args;
use ontographia_adapters::load_ontology_from_path;
use ontographia_core::emit::Dialect;
use ontographia_core::engine::Engine;
use ontographia_core::intent::Intent;
use serde_json::json;

#[derive(Args)]
pub struct BuildArgs {
    /// Path to the ontology file
    #[arg(short, long)]
    pub ontology: PathBuf,

    /// Path to Intent JSON (default: read from stdin)
    #[arg(short, long)]
    pub intent: Option<PathBuf>,

    /// Output dialect: cypher25 (default), cypher5, gql
    #[arg(short, long, default_value = "cypher25")]
    pub dialect: String,

    /// Emit JSON `{"query","params"}` instead of query text + params line
    #[arg(long)]
    pub json: bool,
}

pub fn run(args: BuildArgs) -> Result<(), Box<dyn std::error::Error>> {
    let ontology = load_ontology_from_path(&args.ontology)?;
    let engine = Engine::new(ontology);

    let intent_text = match &args.intent {
        Some(path) => fs::read_to_string(path)?,
        None => {
            let mut buf = String::new();
            io::stdin().read_to_string(&mut buf)?;
            buf
        }
    };
    let intent_json: serde_json::Value = serde_json::from_str(&intent_text)?;
    let intent: Intent = serde_json::from_value(intent_json)?;

    let dialect = parse_dialect(&args.dialect)?;
    let emitted = engine.build(intent, dialect)?;

    if args.json {
        let out = json!({
            "query": emitted.query,
            "params": emitted.params,
        });
        println!("{}", serde_json::to_string_pretty(&out)?);
    } else {
        println!("{}", emitted.query);
        println!("params: {:?}", emitted.params);
    }

    Ok(())
}

fn parse_dialect(name: &str) -> Result<Dialect, String> {
    match name.to_ascii_lowercase().as_str() {
        "cypher25" | "cypher-25" => Ok(Dialect::Cypher25),
        "cypher5" | "cypher-5" => Ok(Dialect::Cypher5),
        "gql" => Ok(Dialect::Gql),
        other => Err(format!(
            "unknown dialect '{other}' (expected cypher25, cypher5, or gql)"
        )),
    }
}
