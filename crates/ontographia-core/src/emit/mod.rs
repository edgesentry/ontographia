mod cypher25;
mod cypher5;
mod gql;

use crate::ast::EmittedQuery;
use crate::error::Result;

pub use cypher25::Cypher25Emitter;
pub use cypher5::Cypher5Emitter;
pub use gql::GqlEmitter;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum Dialect {
    #[default]
    Cypher25,
    Cypher5,
    Gql,
}

impl Dialect {
    /// Accepted dialect names, for error messages.
    pub const EXPECTED: &'static str = "cypher25, cypher5, or gql";
}

impl std::str::FromStr for Dialect {
    type Err = String;

    /// Parse a dialect name (case-insensitive). Unknown names are an error;
    /// there is no silent fallback to `cypher25`.
    fn from_str(name: &str) -> std::result::Result<Self, Self::Err> {
        match name.to_ascii_lowercase().as_str() {
            "cypher25" | "cypher-25" => Ok(Dialect::Cypher25),
            "cypher5" | "cypher-5" => Ok(Dialect::Cypher5),
            "gql" => Ok(Dialect::Gql),
            other => Err(format!(
                "unknown dialect '{other}' (expected {})",
                Dialect::EXPECTED
            )),
        }
    }
}

pub trait QueryEmitter {
    fn emit(&self, ast: &crate::ast::QueryAst, params: &indexmap::IndexMap<String, serde_json::Value>) -> Result<EmittedQuery>;
}

pub fn emit_query(
    dialect: Dialect,
    ast: &crate::ast::QueryAst,
    params: &indexmap::IndexMap<String, serde_json::Value>,
) -> Result<EmittedQuery> {
    match dialect {
        Dialect::Cypher25 => Cypher25Emitter.emit(ast, params),
        Dialect::Cypher5 => Cypher5Emitter.emit(ast, params),
        Dialect::Gql => GqlEmitter.emit(ast, params),
    }
}

#[cfg(test)]
mod tests {
    use super::Dialect;

    #[test]
    fn parses_known_dialects() {
        assert_eq!("cypher25".parse::<Dialect>().unwrap(), Dialect::Cypher25);
        assert_eq!("Cypher-25".parse::<Dialect>().unwrap(), Dialect::Cypher25);
        assert_eq!("cypher5".parse::<Dialect>().unwrap(), Dialect::Cypher5);
        assert_eq!("GQL".parse::<Dialect>().unwrap(), Dialect::Gql);
    }

    #[test]
    fn rejects_unknown_dialect() {
        let err = "cyhper5".parse::<Dialect>().unwrap_err();
        assert!(err.contains("unknown dialect 'cyhper5'"), "{err}");
        assert!(err.contains("expected cypher25, cypher5, or gql"), "{err}");
    }
}
