//! Homebrew installs this program as `otg` (`brew install ontographia`).
//! The release archive also ships a copy of the file named `ontographia`,
//! because the current tap formula looks up that filename. The compiled
//! command name is `otg`.
//!
//! Subcommands today: `build` and `schema`. Read-only Neo4j `execute` is the
//! follow-up tracked in the packaging decision: Intent-only input, generated
//! Cypher only, write clauses rejected before a driver runs (same rule as
//! `python/ontographia/cli.py`). Until that subcommand exists, `execute` is
//! the Python entry point (`ontographia[cli]`).

mod commands;

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
