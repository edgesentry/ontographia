use crate::ast::EmittedQuery;
use crate::emit::cypher25::Cypher25Emitter;
use crate::emit::QueryEmitter;
use crate::error::Result;
use indexmap::IndexMap;

/// Prototype GQL emitter — reuses Cypher 25 structure with GQL session prefix.
pub struct GqlEmitter;

impl QueryEmitter for GqlEmitter {
    fn emit(&self, ast: &crate::ast::QueryAst, params: &IndexMap<String, serde_json::Value>) -> Result<EmittedQuery> {
        let mut emitted = Cypher25Emitter.emit(ast, params)?;
        emitted.query = emitted
            .query
            .replacen("CYPHER 25", "SESSION SET QUERY LANGUAGE GQL", 1);
        Ok(emitted)
    }
}
