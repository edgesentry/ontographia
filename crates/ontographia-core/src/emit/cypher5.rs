use crate::ast::EmittedQuery;
use crate::emit::cypher25::Cypher25Emitter;
use crate::emit::QueryEmitter;
use crate::error::Result;
use indexmap::IndexMap;

pub struct Cypher5Emitter;

impl QueryEmitter for Cypher5Emitter {
    fn emit(&self, ast: &crate::ast::QueryAst, params: &IndexMap<String, serde_json::Value>) -> Result<EmittedQuery> {
        let mut emitted = Cypher25Emitter.emit(ast, params)?;
        emitted.query = emitted
            .query
            .replace("CYPHER 25\n", "CYPHER 5\n")
            .replace("FILTER ", "WHERE ");
        Ok(emitted)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ast::{MatchClause, NodePattern, PatternNode, QueryAst, ReturnExpr, ReturnNode};

    #[test]
    fn uses_where_instead_of_filter() {
        let ast = QueryAst {
            match_clause: MatchClause {
                optional: false,
                patterns: vec![PatternNode {
                    nodes: vec![NodePattern {
                        alias: "p".into(),
                        labels: vec!["Person".into()],
                    }],
                    relationships: vec![],
                }],
            },
            filters: vec![crate::ast::FilterNode {
                alias: "p".into(),
                property: "age".into(),
                op: crate::intent::FilterOp::Gt,
                param_name: "param_0".into(),
            }],
            returns: vec![ReturnNode {
                expr: ReturnExpr::Node {
                    alias: "p".into(),
                },
                alias: None,
            }],
            order_by: None,
            limit: None,
            skip: None,
        };
        let mut params = IndexMap::new();
        params.insert("param_0".into(), serde_json::json!(18));
        let emitted = Cypher5Emitter.emit(&ast, &params).unwrap();
        assert!(emitted.query.starts_with("CYPHER 5"));
        assert!(emitted.query.contains("WHERE "));
    }
}
