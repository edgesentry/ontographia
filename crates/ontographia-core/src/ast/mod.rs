use crate::intent::{AggregateFn, Direction, FilterOp};
use indexmap::IndexMap;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct QueryAst {
    pub match_clause: MatchClause,
    pub filters: Vec<FilterNode>,
    pub returns: Vec<ReturnNode>,
    pub order_by: Option<OrderByNode>,
    pub limit: Option<u32>,
    pub skip: Option<u32>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MatchClause {
    pub optional: bool,
    pub patterns: Vec<PatternNode>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PatternNode {
    pub nodes: Vec<NodePattern>,
    pub relationships: Vec<RelPattern>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct NodePattern {
    pub alias: String,
    pub labels: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RelPattern {
    pub alias: Option<String>,
    pub rel_type: String,
    pub direction: Direction,
    pub min_hops: Option<u32>,
    pub max_hops: Option<u32>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FilterNode {
    pub alias: String,
    pub property: String,
    pub op: FilterOp,
    pub param_name: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ReturnNode {
    pub expr: ReturnExpr,
    pub alias: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum ReturnExpr {
    Property { alias: String, property: String },
    Node { alias: String },
    Aggregate {
        func: AggregateFn,
        alias: String,
        property: Option<String>,
    },
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct OrderByNode {
    pub alias: String,
    pub property: Option<String>,
    pub descending: bool,
}

#[derive(Debug, Clone, PartialEq, Default)]
pub struct EmittedQuery {
    pub query: String,
    pub params: IndexMap<String, serde_json::Value>,
}
