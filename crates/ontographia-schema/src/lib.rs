//! COM-derived Neo4j graph schema utilities.
//!
//! - [`GraphSchema::from_com`] — derive expected labels and relationship types from COM
//! - [`emit::emit_cypher25_constraints`] — generate `CREATE CONSTRAINT` DDL
//! - [`diff::diff`] — compare expected schema against an offline Neo4j catalog snapshot

pub mod diff;
pub mod emit;
pub mod error;
pub mod from_com;
pub mod model;

pub use diff::{diff, diff_has_errors, SchemaDiff};
pub use emit::emit_cypher25_constraints;
pub use error::{Result, SchemaError};
pub use model::{GraphSchema, GraphSnapshot, LabelSchema, RelSchema};
