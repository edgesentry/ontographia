use std::path::PathBuf;

use ontographia_adapters::load_ontology_from_path;
use ontographia_core::emit::Dialect;
use ontographia_core::engine::Engine;
use ontographia_core::intent::{
    Direction, FilterExpr, FilterOp, Intent, NodeRef, ReturnItem, TraverseStep,
};

fn sample_intent() -> Intent {
    Intent {
        start: NodeRef {
            class: "Product".into(),
            alias: "product".into(),
        },
        traverse: vec![
            TraverseStep {
                relationship: "has_part".into(),
                direction: Direction::Out,
                to: NodeRef {
                    class: "Part".into(),
                    alias: "part".into(),
                },
                min_hops: None,
                max_hops: None,
            },
            TraverseStep {
                relationship: "supplied_by".into(),
                direction: Direction::Out,
                to: NodeRef {
                    class: "Supplier".into(),
                    alias: "supplier".into(),
                },
                min_hops: None,
                max_hops: None,
            },
        ],
        filter: vec![FilterExpr {
            alias: "product".into(),
            property: "sku".into(),
            op: FilterOp::Eq,
            value: serde_json::json!("SPX-100"),
        }],
        not_exists: vec![],
        r#return: vec![ReturnItem {
            alias: "supplier".into(),
            property: Some("name".into()),
            aggregate: None,
            as_name: Some("supplier_name".into()),
        }],
        order_by: None,
        limit: Some(20),
        skip: None,
        optional: false,
    }
}

fn example_path(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../examples")
        .join(name)
}

#[test]
fn end_to_end_native_yaml_cypher25() {
    let ontology = load_ontology_from_path(example_path("manufacturing.native.yaml")).unwrap();
    let engine = Engine::new(ontology);
    let emitted = engine.build(sample_intent(), Dialect::Cypher25).unwrap();
    assert!(emitted.query.starts_with("CYPHER 25"));
    assert!(emitted.query.contains("FILTER product.sku = $param_0"));
    assert_eq!(
        emitted.params.get("param_0"),
        Some(&serde_json::json!("SPX-100"))
    );
}

/// An Intent without `not_exists` keeps the exact 0.1.9 output (line layout,
/// clause order, parameter names).
#[test]
fn intent_without_not_exists_is_byte_identical_to_0_1_9() {
    let ontology = load_ontology_from_path(example_path("manufacturing.native.yaml")).unwrap();
    let engine = Engine::new(ontology);
    let emitted = engine.build(sample_intent(), Dialect::Cypher25).unwrap();
    assert_eq!(
        emitted.query,
        "CYPHER 25\n\
         MATCH (product:Product)-[:has_part]->(part:Part)-[:supplied_by]->(supplier:Supplier)\n\
         FILTER product.sku = $param_0\n\
         RETURN supplier.name AS supplier_name\n\
         LIMIT 20"
    );
    assert_eq!(
        emitted.params.keys().cloned().collect::<Vec<_>>(),
        vec!["param_0".to_string()]
    );
    assert_eq!(
        emitted.params.get("param_0"),
        Some(&serde_json::json!("SPX-100"))
    );
}

#[test]
fn end_to_end_turtle_owl() {
    let ontology = load_ontology_from_path(example_path("manufacturing.owl.ttl")).unwrap();
    let engine = Engine::new(ontology);
    let emitted = engine.build(sample_intent(), Dialect::Cypher25).unwrap();
    assert!(emitted.query.contains("Product"));
    assert!(emitted.query.contains("has_part"));
}

#[test]
fn end_to_end_jsonld() {
    let ontology = load_ontology_from_path(example_path("manufacturing.jsonld")).unwrap();
    let engine = Engine::new(ontology);
    let emitted = engine.build(sample_intent(), Dialect::Cypher25).unwrap();
    assert!(emitted.query.contains("RETURN"));
}

#[test]
fn end_to_end_linkml() {
    let ontology = load_ontology_from_path(example_path("manufacturing.linkml.yaml")).unwrap();
    let engine = Engine::new(ontology);
    let emitted = engine.build(sample_intent(), Dialect::Cypher25).unwrap();
    assert!(emitted.query.contains("LIMIT 20"));
}

fn not_exists_intent() -> serde_json::Value {
    let bytes = std::fs::read(example_path("part_usage_not_exists.json")).unwrap();
    serde_json::from_slice(&bytes).unwrap()
}

#[test]
fn not_exists_cypher25_end_to_end() {
    let ontology = load_ontology_from_path(example_path("part_usage.native.yaml")).unwrap();
    let engine = Engine::new(ontology);
    let emitted = engine
        .build_from_json(&not_exists_intent(), Dialect::Cypher25)
        .unwrap();

    assert_eq!(
        emitted.query,
        "CYPHER 25\n\
         MATCH (part:Part)\n\
         FILTER part.category_slug = $param_0 AND NOT EXISTS { MATCH (u:Usage)-[:USES_ITEM]->(part) FILTER u.match_method = $param_1 }\n\
         RETURN part.name AS part\n\
         LIMIT 200"
    );
    assert_eq!(emitted.params.len(), 2);
    assert_eq!(
        emitted.params.get("param_0"),
        Some(&serde_json::json!("fasteners-and-hardware"))
    );
    assert_eq!(
        emitted.params.get("param_1"),
        Some(&serde_json::json!("exact"))
    );
}

#[test]
fn not_exists_cypher5_end_to_end() {
    let ontology = load_ontology_from_path(example_path("part_usage.native.yaml")).unwrap();
    let engine = Engine::new(ontology);
    let emitted = engine
        .build_from_json(&not_exists_intent(), Dialect::Cypher5)
        .unwrap();

    assert_eq!(
        emitted.query,
        "CYPHER 5\n\
         MATCH (part:Part)\n\
         WHERE part.category_slug = $param_0 AND NOT EXISTS { MATCH (u:Usage)-[:USES_ITEM]->(part) WHERE u.match_method = $param_1 }\n\
         RETURN part.name AS part\n\
         LIMIT 200"
    );
    assert!(!emitted.query.contains("FILTER"), "{}", emitted.query);
}

#[test]
fn dialect_cypher5_uses_where() {
    let ontology = load_ontology_from_path(example_path("manufacturing.native.yaml")).unwrap();
    let engine = Engine::new(ontology);
    let emitted = engine.build(sample_intent(), Dialect::Cypher5).unwrap();
    assert!(emitted.query.starts_with("CYPHER 5"));
    assert!(emitted.query.contains("WHERE "));
}

#[test]
fn dialect_gql_prefix() {
    let ontology = load_ontology_from_path(example_path("manufacturing.native.yaml")).unwrap();
    let engine = Engine::new(ontology);
    let emitted = engine.build(sample_intent(), Dialect::Gql).unwrap();
    assert!(emitted.query.starts_with("SESSION SET QUERY LANGUAGE GQL"));
}

#[test]
fn neo4j_cypher25_query_shape() {
    let ontology = load_ontology_from_path(example_path("manufacturing.native.yaml")).unwrap();
    let engine = Engine::new(ontology);
    let emitted = engine.build(sample_intent(), Dialect::Cypher25).unwrap();

    let lines: Vec<&str> = emitted.query.lines().collect();
    assert_eq!(lines[0], "CYPHER 25");
    assert!(lines[1].starts_with("MATCH"));
    assert!(lines.iter().any(|l| l.starts_with("FILTER")));
    assert!(lines.iter().any(|l| l.starts_with("RETURN")));
    assert!(lines.iter().any(|l| l.starts_with("LIMIT")));
    assert!(!emitted.query.contains(";"));
    for (key, _) in &emitted.params {
        assert!(emitted.query.contains(&format!("${}", key)));
    }
}
