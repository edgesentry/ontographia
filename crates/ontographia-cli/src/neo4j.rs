//! Read-only Neo4j bolt execution for `otg execute`.
//!
//! Queries run through `neo4rs::Graph::execute_read`, which sets Bolt `mode: "r"`
//! (the driver equivalent of the Python driver's `READ_ACCESS` / `execute_read`).
//! The deny list is applied again here so a write query is not handed to the driver
//! even if a caller skips the earlier check.

use crate::safety::assert_read_only_cypher;
use neo4rs::{query, BoltType, ConfigBuilder, Graph, Node, Relation, UnboundedRelation};
use serde_json::{Map, Value};
use std::collections::BTreeMap;

pub struct Neo4jSettings {
    pub uri: String,
    pub username: String,
    pub password: String,
    pub database: Option<String>,
}

pub fn execute_read(
    settings: &Neo4jSettings,
    cypher: &str,
    params: &Map<String, Value>,
    row_limit: i64,
) -> Result<Vec<BTreeMap<String, Value>>, String> {
    assert_read_only_cypher(cypher).map_err(|err| err.to_string())?;
    // rustls 0.23 panics on TLS handshakes unless a process-wide provider is installed.
    // bolt:// does not use it; neo4j+s:// and bolt+s:// do.
    let _ = rustls::crypto::ring::default_provider().install_default();

    let mut builder = ConfigBuilder::default()
        .uri(settings.uri.clone())
        .user(settings.username.clone())
        .password(settings.password.clone())
        .max_connections(1);
    if let Some(database) = settings.database.as_deref().filter(|db| !db.is_empty()) {
        builder = builder.db(database);
    }
    let fetch = usize::try_from(row_limit.max(1)).unwrap_or(usize::MAX);
    builder = builder.fetch_size(fetch);
    let config = builder
        .build()
        .map_err(|err| format!("failed to open Neo4j driver: {err}"))?;
    let graph =
        Graph::connect(config).map_err(|err| format!("failed to open Neo4j driver: {err}"))?;

    let runtime = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
        .map_err(|err| format!("failed to open Neo4j driver: {err}"))?;
    runtime
        .block_on(run_query(&graph, cypher, params, row_limit))
        .map_err(|err| redact(&err, &settings.password))
}

async fn run_query(
    graph: &Graph,
    cypher: &str,
    params: &Map<String, Value>,
    row_limit: i64,
) -> Result<Vec<BTreeMap<String, Value>>, String> {
    let mut statement = query(cypher);
    for (key, value) in params {
        let bolt = BoltType::try_from(value.clone()).map_err(|err| err.to_string())?;
        statement = statement.param(key, bolt);
    }
    let mut stream = graph
        .execute_read(statement)
        .await
        .map_err(|err| err.to_string())?;
    let mut rows = Vec::new();
    if row_limit <= 0 {
        return Ok(rows);
    }
    let limit = usize::try_from(row_limit).unwrap_or(usize::MAX);
    while rows.len() < limit {
        match stream.next().await.map_err(|err| err.to_string())? {
            Some(row) => rows.push(row_to_json(&row)?),
            None => break,
        }
    }
    Ok(rows)
}

fn row_to_json(row: &neo4rs::Row) -> Result<BTreeMap<String, Value>, String> {
    let names: Vec<String> = row
        .keys()
        .into_iter()
        .map(|key| key.value.clone())
        .collect();
    let mut record = BTreeMap::new();
    for name in names {
        record.insert(name.clone(), cell_value(row, &name)?);
    }
    Ok(record)
}

fn cell_value(row: &neo4rs::Row, key: &str) -> Result<Value, String> {
    if let Ok(node) = row.get::<Node>(key) {
        return node_value(&node);
    }
    if let Ok(relation) = row.get::<Relation>(key) {
        return relation_value(&relation);
    }
    if let Ok(relation) = row.get::<UnboundedRelation>(key) {
        return unbounded_value(&relation);
    }
    row.get::<Value>(key)
        .map_err(|err| format!("column {key}: {err}"))
}

fn node_value(node: &Node) -> Result<Value, String> {
    let mut labels: Vec<String> = node.labels().into_iter().map(str::to_string).collect();
    labels.sort();
    let mut properties = Map::new();
    for key in node.keys() {
        let value = node
            .get::<Value>(key)
            .map_err(|err| format!("node property {key}: {err}"))?;
        properties.insert(key.to_string(), value);
    }
    Ok(serde_json::json!({
        "labels": labels,
        "properties": properties,
    }))
}

fn relation_value(relation: &Relation) -> Result<Value, String> {
    let mut properties = Map::new();
    for key in relation.keys() {
        let value = relation
            .get::<Value>(key)
            .map_err(|err| format!("relationship property {key}: {err}"))?;
        properties.insert(key.to_string(), value);
    }
    Ok(serde_json::json!({
        "type": relation.typ(),
        "properties": properties,
    }))
}

fn unbounded_value(relation: &UnboundedRelation) -> Result<Value, String> {
    let mut properties = Map::new();
    for key in relation.keys() {
        let value = relation
            .get::<Value>(key)
            .map_err(|err| format!("relationship property {key}: {err}"))?;
        properties.insert(key.to_string(), value);
    }
    Ok(serde_json::json!({
        "type": relation.typ(),
        "properties": properties,
    }))
}

fn redact(message: &str, secret: &str) -> String {
    if secret.is_empty() {
        message.to_string()
    } else {
        message.replace(secret, "***")
    }
}

#[cfg(test)]
mod tests {
    use super::{execute_read, Neo4jSettings};
    use serde_json::Map;

    #[test]
    fn write_cypher_is_rejected_before_a_connection() {
        let err = execute_read(
            &Neo4jSettings {
                uri: "bolt://127.0.0.1:1".to_string(),
                username: "neo4j".to_string(),
                password: "secret".to_string(),
                database: None,
            },
            "CREATE (n:X {name: 'nope'}) RETURN n",
            &Map::new(),
            1,
        )
        .unwrap_err();
        assert!(err.contains("read-only"), "{err}");
        assert!(!err.contains("secret"), "{err}");
    }
}
