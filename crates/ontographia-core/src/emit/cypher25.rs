use crate::ast::{EmittedQuery, FilterNode, MatchClause, NodePattern, PatternNode, QueryAst, RelPattern, ReturnExpr, ReturnNode};
use crate::emit::QueryEmitter;
use crate::error::Result;
use crate::intent::Direction;
use indexmap::IndexMap;

pub struct Cypher25Emitter;

impl QueryEmitter for Cypher25Emitter {
    fn emit(&self, ast: &QueryAst, params: &IndexMap<String, serde_json::Value>) -> Result<EmittedQuery> {
        let mut parts = vec!["CYPHER 25".to_string()];

        let match_kw = if ast.match_clause.optional {
            "OPTIONAL MATCH"
        } else {
            "MATCH"
        };
        parts.push(format!("{} {}", match_kw, render_patterns(&ast.match_clause)));

        if !ast.filters.is_empty() {
            parts.push(format!("FILTER {}", render_filters(&ast.filters)));
        }

        parts.push(format!("RETURN {}", render_returns(&ast.returns)));

        if let Some(order) = &ast.order_by {
            let prop = order
                .property
                .as_ref()
                .map(|p| format!(".{}", p))
                .unwrap_or_default();
            let dir = if order.descending { " DESC" } else { " ASC" };
            parts.push(format!("ORDER BY {}{}{}", order.alias, prop, dir));
        }

        if let Some(skip) = ast.skip {
            parts.push(format!("SKIP {}", skip));
        }
        if let Some(limit) = ast.limit {
            parts.push(format!("LIMIT {}", limit));
        }

        Ok(EmittedQuery {
            query: parts.join("\n"),
            params: params.clone(),
        })
    }
}

fn render_patterns(match_clause: &MatchClause) -> String {
    match_clause
        .patterns
        .iter()
        .map(render_pattern)
        .collect::<Vec<_>>()
        .join(", ")
}

fn render_pattern(pattern: &PatternNode) -> String {
    let mut out = String::new();
    for (i, node) in pattern.nodes.iter().enumerate() {
        if i > 0 {
            let rel = &pattern.relationships[i - 1];
            out.push_str(&render_rel(rel));
        }
        out.push_str(&render_node(node));
    }
    out
}

fn render_node(node: &NodePattern) -> String {
    let labels = node
        .labels
        .iter()
        .map(|l| format!(":{}", l))
        .collect::<Vec<_>>()
        .join("");
    format!("({}{})", node.alias, labels)
}

fn render_rel(rel: &RelPattern) -> String {
    let rel_part = if let (Some(min), Some(max)) = (rel.min_hops, rel.max_hops) {
        if min == max && min == 1 {
            format!(":{}", rel.rel_type)
        } else {
            format!(":{}*{}..{}", rel.rel_type, min, max)
        }
    } else {
        format!(":{}", rel.rel_type)
    };

    match rel.direction {
        Direction::Out => format!("-[{}]->", rel_part),
        Direction::In => format!("<-[{}]-", rel_part),
        Direction::Both => format!("-[{}]-", rel_part),
    }
}

fn render_filters(filters: &[FilterNode]) -> String {
    filters
        .iter()
        .map(|f| {
            let op = match f.op {
                crate::intent::FilterOp::Eq => "=",
                crate::intent::FilterOp::Neq => "<>",
                crate::intent::FilterOp::Lt => "<",
                crate::intent::FilterOp::Lte => "<=",
                crate::intent::FilterOp::Gt => ">",
                crate::intent::FilterOp::Gte => ">=",
                crate::intent::FilterOp::In => "IN",
                crate::intent::FilterOp::Contains => "CONTAINS",
            };
            if matches!(f.op, crate::intent::FilterOp::In) {
                format!("{}.{} {} ${}", f.alias, f.property, op, f.param_name)
            } else if matches!(f.op, crate::intent::FilterOp::Contains) {
                format!("{}.{} CONTAINS ${}", f.alias, f.property, f.param_name)
            } else {
                format!("{}.{} {} ${}", f.alias, f.property, op, f.param_name)
            }
        })
        .collect::<Vec<_>>()
        .join(" AND ")
}

fn render_returns(returns: &[ReturnNode]) -> String {
    returns
        .iter()
        .map(|r| match &r.expr {
            ReturnExpr::Property { alias, property } => {
                let base = format!("{}.{}", alias, property);
                r.alias
                    .as_ref()
                    .map(|a| format!("{} AS {}", base, a))
                    .unwrap_or(base)
            }
            ReturnExpr::Node { alias } => r
                .alias
                .as_ref()
                .map(|a| format!("{} AS {}", alias, a))
                .unwrap_or_else(|| alias.clone()),
            ReturnExpr::Aggregate {
                func,
                alias,
                property,
            } => {
                let inner = match (func, property) {
                    (crate::intent::AggregateFn::Count, None) => format!("count({})", alias),
                    (crate::intent::AggregateFn::Count, Some(p)) => {
                        format!("count({}.{})", alias, p)
                    }
                    (crate::intent::AggregateFn::Collect, Some(p)) => {
                        format!("collect({}.{})", alias, p)
                    }
                    (crate::intent::AggregateFn::Collect, None) => format!("collect({})", alias),
                };
                r.alias
                    .as_ref()
                    .map(|a| format!("{} AS {}", inner, a))
                    .unwrap_or(inner)
            }
        })
        .collect::<Vec<_>>()
        .join(", ")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ast::{FilterNode, PatternNode};
    use crate::intent::{AggregateFn, FilterOp};

    #[test]
    fn emits_cypher25_with_filter() {
        let ast = QueryAst {
            match_clause: MatchClause {
                optional: false,
                patterns: vec![PatternNode {
                    nodes: vec![
                        NodePattern {
                            alias: "p".into(),
                            labels: vec!["Person".into()],
                        },
                        NodePattern {
                            alias: "friend".into(),
                            labels: vec!["Person".into()],
                        },
                    ],
                    relationships: vec![RelPattern {
                        alias: None,
                        rel_type: "knows".into(),
                        direction: Direction::Out,
                        min_hops: None,
                        max_hops: None,
                    }],
                }],
            },
            filters: vec![FilterNode {
                alias: "p".into(),
                property: "age".into(),
                op: FilterOp::Gte,
                param_name: "param_0".into(),
            }],
            returns: vec![ReturnNode {
                expr: ReturnExpr::Property {
                    alias: "friend".into(),
                    property: "name".into(),
                },
                alias: Some("name".into()),
            }],
            order_by: None,
            limit: Some(10),
            skip: None,
        };

        let mut params = IndexMap::new();
        params.insert("param_0".into(), serde_json::json!(30));

        let emitted = Cypher25Emitter.emit(&ast, &params).unwrap();
        assert!(emitted.query.starts_with("CYPHER 25"));
        assert!(emitted.query.contains("FILTER p.age >= $param_0"));
        assert!(emitted.query.contains("LIMIT 10"));
    }

    #[test]
    fn emits_variable_length_path() {
        let ast = QueryAst {
            match_clause: MatchClause {
                optional: false,
                patterns: vec![PatternNode {
                    nodes: vec![
                        NodePattern {
                            alias: "a".into(),
                            labels: vec!["Person".into()],
                        },
                        NodePattern {
                            alias: "b".into(),
                            labels: vec!["Person".into()],
                        },
                    ],
                    relationships: vec![RelPattern {
                        alias: None,
                        rel_type: "knows".into(),
                        direction: Direction::Out,
                        min_hops: Some(1),
                        max_hops: Some(3),
                    }],
                }],
            },
            filters: vec![],
            returns: vec![ReturnNode {
                expr: ReturnExpr::Node {
                    alias: "b".into(),
                },
                alias: None,
            }],
            order_by: None,
            limit: None,
            skip: None,
        };

        let emitted = Cypher25Emitter.emit(&ast, &IndexMap::new()).unwrap();
        assert!(emitted.query.contains("knows*1..3"));
    }

    #[test]
    fn emits_aggregate() {
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
            filters: vec![],
            returns: vec![ReturnNode {
                expr: ReturnExpr::Aggregate {
                    func: AggregateFn::Count,
                    alias: "p".into(),
                    property: None,
                },
                alias: Some("total".into()),
            }],
            order_by: None,
            limit: None,
            skip: None,
        };

        let emitted = Cypher25Emitter.emit(&ast, &IndexMap::new()).unwrap();
        assert!(emitted.query.contains("count(p) AS total"));
    }
}
