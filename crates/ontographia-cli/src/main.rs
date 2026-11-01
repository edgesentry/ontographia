//! Homebrew installs this program as `otg` (`brew install ontographia`).
//! The release archive also ships a copy of the file named `ontographia`,
//! because the current tap formula looks up that filename. The compiled
//! command name is `otg`.
//!
//! Subcommands: `build`, `schema`, and read-only Neo4j `execute`.
//! `execute` accepts Intent JSON only. Write clauses and variable-length hop
//! ranges are rejected before a driver runs (same rules as
//! `python/ontographia/cli.py`). The Python entry point (`ontographia[cli]`)
//! remains for pip and uvx.

mod commands;
mod neo4j;
mod output;
mod read_only;
mod safety;

use clap::{Parser, Subcommand};
use std::process;

#[derive(Parser)]
#[command(
    name = env!("CARGO_BIN_NAME"),
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
    /// Compile Intent JSON and run it read-only against Neo4j
    Execute(commands::execute::ExecuteArgs),
}

fn main() {
    let cli = Cli::parse();
    match cli.command {
        Commands::Execute(args) => {
            if let Err(err) = commands::execute::run(args) {
                eprintln!("otg: {err}");
                process::exit(err.code);
            }
        }
        Commands::Build(args) => {
            if let Err(err) = commands::build::run(args) {
                eprintln!("error: {err}");
                process::exit(1);
            }
        }
        Commands::Schema(args) => {
            if let Err(err) = commands::schema::run(args) {
                eprintln!("error: {err}");
                process::exit(1);
            }
        }
    }
}
