mod commands;

use clap::{Parser, Subcommand};
use std::process;

#[derive(Parser)]
#[command(
    name = "ontographia",
    version,
    about = "Ontology-driven deterministic Cypher 25 query builder"
)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Build Cypher from an ontology file and Intent JSON
    Build(commands::build::BuildArgs),
    /// Emit Neo4j schema artifacts (constraints, schema.json) from an ontology
    Schema(commands::schema::SchemaArgs),
}

fn main() {
    let cli = Cli::parse();
    let result = match cli.command {
        Commands::Build(args) => commands::build::run(args),
        Commands::Schema(args) => commands::schema::run(args),
    };
    if let Err(err) = result {
        eprintln!("error: {err}");
        process::exit(1);
    }
}
