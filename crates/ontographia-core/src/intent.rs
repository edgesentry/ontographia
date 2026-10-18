use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Intent {
    pub start: NodeRef,
    #[serde(default)]
    pub traverse: Vec<TraverseStep>,
    #[serde(default)]
    pub filter: Vec<FilterExpr>,
    pub r#return: Vec<ReturnItem>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub order_by: Option<OrderBy>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub limit: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub skip: Option<u32>,
    #[serde(default)]
    pub optional: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct NodeRef {
    pub class: String,
    pub alias: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct TraverseStep {
    pub relationship: String,
    pub direction: Direction,
    pub to: NodeRef,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub min_hops: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub max_hops: Option<u32>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "lowercase")]
pub enum Direction {
    Out,
    In,
    Both,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct FilterExpr {
    pub alias: String,
    pub property: String,
    pub op: FilterOp,
    pub value: serde_json::Value,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "lowercase")]
pub enum FilterOp {
    Eq,
    Neq,
    Lt,
    Lte,
    Gt,
    Gte,
    In,
    Contains,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ReturnItem {
    pub alias: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub property: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub aggregate: Option<AggregateFn>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub as_name: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "lowercase")]
pub enum AggregateFn {
    Count,
    Collect,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct OrderBy {
    pub alias: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub property: Option<String>,
    #[serde(default)]
    pub descending: bool,
}

#[cfg(test)]
mod tests {
    use super::Intent;

    fn parse(v: serde_json::Value) -> Result<Intent, serde_json::Error> {
        serde_json::from_value(v)
    }

    #[test]
    fn accepts_known_keys() {
        let intent = parse(serde_json::json!({
            "start": {"class": "Product", "alias": "p"},
            "traverse": [{"relationship": "has_part", "direction": "out",
                          "to": {"class": "Part", "alias": "part"}, "min_hops": 1, "max_hops": 1}],
            "filter": [{"alias": "p", "property": "sku", "op": "eq", "value": "SPX-100"}],
            "return": [{"alias": "part", "property": "name", "as_name": "n"}],
            "order_by": {"alias": "part", "property": "name", "descending": true},
            "limit": 20, "skip": 0, "optional": false
        }));
        assert!(intent.is_ok(), "{intent:?}");
    }

    #[test]
    fn rejects_unknown_top_level_key() {
        // Regression for #81: `filters` used to be silently ignored, dropping the filter.
        let err = parse(serde_json::json!({
            "start": {"class": "Product", "alias": "p"},
            "filters": [{"alias": "p", "property": "sku", "op": "eq", "value": "x"}],
            "return": [{"alias": "p"}]
        }))
        .unwrap_err()
        .to_string();
        assert!(err.contains("unknown field `filters`"), "{err}");
    }

    #[test]
    fn rejects_unknown_nested_keys() {
        let cases = [
            ("as", serde_json::json!({
                "start": {"class": "P", "alias": "p"},
                "return": [{"alias": "p", "as": "x"}]})),
            ("label", serde_json::json!({
                "start": {"class": "P", "alias": "p", "label": "x"},
                "return": [{"alias": "p"}]})),
            ("dir", serde_json::json!({
                "start": {"class": "P", "alias": "p"},
                "traverse": [{"relationship": "r", "direction": "out", "dir": "out",
                              "to": {"class": "Q", "alias": "q"}}],
                "return": [{"alias": "p"}]})),
            ("operator", serde_json::json!({
                "start": {"class": "P", "alias": "p"},
                "filter": [{"alias": "p", "property": "a", "op": "eq", "value": 1, "operator": "="}],
                "return": [{"alias": "p"}]})),
            ("desc", serde_json::json!({
                "start": {"class": "P", "alias": "p"},
                "return": [{"alias": "p"}],
                "order_by": {"alias": "p", "desc": true}})),
        ];
        for (key, v) in cases {
            let err = parse(v).unwrap_err().to_string();
            assert!(err.contains(&format!("unknown field `{key}`")), "{key}: {err}");
        }
    }
}
