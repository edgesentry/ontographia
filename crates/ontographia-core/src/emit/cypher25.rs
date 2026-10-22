use crate::ast::{EmittedQuery, FilterNode, MatchClause, NodePattern, PatternNode, QueryAst, RelPattern, ReturnExpr, ReturnNode};
use crate::emit::QueryEmitter;
use crate::error::Result;
use crate::intent::Direction;
use indexmap::IndexMap;

pub struct Cypher25Emitter;

fn is_safe_unquoted_ident(name: &str) -> bool {
    let mut chars = name.chars();
    match chars.next() {
        Some(c) if c.is_ascii_alphabetic() || c == '_' => {}
        _ => return false,
    }
    chars.all(|c| c.is_ascii_alphanumeric() || c == '_')
}

/// Emit a Cypher identifier. Safe unquoted names stay unquoted (stable output);
/// anything else is backtick-quoted with embedded backticks doubled so hostile
/// Intent fragments cannot break out of identifier positions.
pub(crate) fn render_ident(name: &str) -> String {
    if is_safe_unquoted_ident(name) {
        name.to_string()
    } else {
        format!("`{}`", name.replace('`', "``"))
    }
}

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
                .map(|p| format!(".{}", render_ident(p)))
                .unwrap_or_default();
            // Direction is only ASC/DESC (from a boolean on the AST).
            let dir = if order.descending { " DESC" } else { " ASC" };
            parts.push(format!(
                "ORDER BY {}{}{}",
                render_ident(&order.alias),
                prop,
                dir
            ));
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
        .map(|l| format!(":{}", render_ident(l)))
        .collect::<Vec<_>>()
        .join("");
    format!("({}{})", render_ident(&node.alias), labels)
}

fn render_rel(rel: &RelPattern) -> String {
    let ty = render_ident(&rel.rel_type);
    let rel_part = if let (Some(min), Some(max)) = (rel.min_hops, rel.max_hops) {
        if min == max && min == 1 {
            format!(":{}", ty)
        } else {
            format!(":{}*{}..{}", ty, min, max)
        }
    } else {
        format!(":{}", ty)
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
            let left = format!("{}.{}", render_ident(&f.alias), render_ident(&f.property));
            if matches!(f.op, crate::intent::FilterOp::In) {
                format!("{} {} ${}", left, op, f.param_name)
            } else if matches!(f.op, crate::intent::FilterOp::Contains) {
                format!("{} CONTAINS ${}", left, f.param_name)
            } else {
                format!("{} {} ${}", left, op, f.param_name)
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
                let base = format!("{}.{}", render_ident(alias), render_ident(property));
                r.alias
                    .as_ref()
                    .map(|a| format!("{} AS {}", base, render_ident(a)))
                    .unwrap_or(base)
            }
            ReturnExpr::Node { alias } => r
                .alias
                .as_ref()
                .map(|a| format!("{} AS {}", render_ident(alias), render_ident(a)))
                .unwrap_or_else(|| render_ident(alias)),
            ReturnExpr::Aggregate {
                func,
                alias,
                property,
            } => {
                let a = render_ident(alias);
                let inner = match (func, property) {
                    (crate::intent::AggregateFn::Count, None) => format!("count({})", a),
                    (crate::intent::AggregateFn::Count, Some(p)) => {
                        format!("count({}.{})", a, render_ident(p))
                    }
                    (crate::intent::AggregateFn::Collect, Some(p)) => {
                        format!("collect({}.{})", a, render_ident(p))
                    }
                    (crate::intent::AggregateFn::Collect, None) => format!("collect({})", a),
                };
                r.alias
                    .as_ref()
                    .map(|as_name| format!("{} AS {}", inner, render_ident(as_name)))
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

    /// Defense-in-depth: even if a hostile identifier somehow reaches the
    /// emitter (bypassing Intent validation), it must be backtick-quoted so
    /// spaces / comments / RETURN fragments cannot break out of the identifier.
    #[test]
    fn quotes_hostile_as_name_and_alias() {
        let hostile_as = "name` RETURN 1 //";
        let hostile_alias = "p} //";
        let ast = QueryAst {
            match_clause: MatchClause {
                optional: false,
                patterns: vec![PatternNode {
                    nodes: vec![NodePattern {
                        alias: hostile_alias.into(),
                        labels: vec!["Person".into()],
                    }],
                    relationships: vec![],
                }],
            },
            filters: vec![],
            returns: vec![ReturnNode {
                expr: ReturnExpr::Property {
                    alias: hostile_alias.into(),
                    property: "name".into(),
                },
                alias: Some(hostile_as.into()),
            }],
            order_by: Some(crate::ast::OrderByNode {
                alias: hostile_as.into(),
                property: None,
                descending: false,
            }),
            limit: Some(1),
            skip: None,
        };

        let emitted = Cypher25Emitter.emit(&ast, &IndexMap::new()).unwrap();
        let q = &emitted.query;

        assert!(
            q.contains(&format!("({}:Person)", render_ident(hostile_alias))),
            "alias should be quoted: {q}"
        );
        assert!(
            q.contains(&format!("AS {}", render_ident(hostile_as))),
            "as_name should be quoted: {q}"
        );
        assert!(
            q.contains(&format!("ORDER BY {} ASC", render_ident(hostile_as))),
            "order_by should be quoted: {q}"
        );
        // Embedded backtick doubled inside the quoted as_name.
        assert!(q.contains("`name`` RETURN 1 //`"), "{q}");
        // Unquoted breakout must not appear (would inject a second RETURN clause).
        assert!(
            !q.contains("AS name` RETURN 1 //"),
            "unquoted hostile as_name leaked: {q}"
        );
    }

    #[test]
    fn render_ident_leaves_safe_names_unquoted() {
        assert_eq!(render_ident("supplier_name"), "supplier_name");
        assert_eq!(render_ident("p"), "p");
        assert_eq!(render_ident("a b"), "`a b`");
        assert_eq!(render_ident("x`y"), "`x``y`");
    }
}
