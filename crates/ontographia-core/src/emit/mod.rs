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
