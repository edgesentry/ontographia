pub mod ast;
pub mod builder;
pub mod com;
pub mod emit;
pub mod engine;
pub mod error;
pub mod intent;
pub mod schema_gen;
pub mod validate;

pub use com::CanonicalOntology;
pub use engine::Engine;
pub use error::{OntographiaError, Result};
pub use intent::Intent;
pub use emit::Dialect;
