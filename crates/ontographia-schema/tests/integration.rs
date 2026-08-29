use std::collections::BTreeSet;
use std::fs;
use std::path::PathBuf;

use ontographia_adapters::load_ontology_from_path;
use ontographia_schema::{
    diff, diff_has_errors, emit_cypher25_constraints, GraphSchema, GraphSnapshot,
};

fn example_path(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../examples")
        .join(name)
}

fn normalize_unique_requirements(cypher: &str) -> BTreeSet<String> {
    cypher
        .lines()
        .filter_map(|line| {
            let line = line.trim();
            // FOR (p:Product) REQUIRE p.sku IS UNIQUE;
            let rest = line.strip_prefix("FOR (")?;
            let after_label = rest.split_once(") REQUIRE ")?;
            let label = after_label.0.split(':').nth(1)?;
            let prop_part = after_label.1.strip_suffix(" IS UNIQUE;")?;
            let property = prop_part.split('.').nth(1)?;
            Some(format!("{label}.{property}"))
        })
        .collect()
}

#[test]
fn manufacturing_schema_from_com() {
    let ontology = load_ontology_from_path(example_path("manufacturing.native.yaml")).unwrap();
    let schema = GraphSchema::from_com(&ontology);

    assert_eq!(schema.labels.len(), 7);
    assert_eq!(schema.relationship_types.len(), 7);
    assert!(schema.labels.contains_key("Product"));
    assert!(schema.relationship_types.contains_key("has_part"));
}

#[test]
fn manufacturing_unique_properties() {
    let ontology = load_ontology_from_path(example_path("manufacturing.native.yaml")).unwrap();
    let schema = GraphSchema::from_com(&ontology);

    assert_eq!(
        schema.labels["Product"].unique_properties,
        vec!["sku".to_string()]
    );
    assert_eq!(
        schema.labels["Part"].unique_properties,
        vec!["part_number".to_string()]
    );
    assert_eq!(
        schema.labels["Lot"].unique_properties,
        vec!["lot_id".to_string()]
    );
    assert_eq!(
        schema.labels["Supplier"].unique_properties,
        vec!["name".to_string()]
    );
}

#[test]
fn emitted_constraints_match_seed_semantics() {
    let ontology = load_ontology_from_path(example_path("manufacturing.native.yaml")).unwrap();
    let schema = GraphSchema::from_com(&ontology);
    let emitted = emit_cypher25_constraints(&schema);

    let seed = fs::read_to_string(example_path("neo4j/seed.cypher")).unwrap();
    let expected = normalize_unique_requirements(&seed);
    let actual = normalize_unique_requirements(&emitted);

    assert_eq!(actual, expected);
}

#[test]
fn snapshot_matches_manufacturing_schema() {
    let ontology = load_ontology_from_path(example_path("manufacturing.native.yaml")).unwrap();
    let schema = GraphSchema::from_com(&ontology);

    let snapshot_text = fs::read_to_string(example_path("neo4j/catalog.snapshot.json")).unwrap();
    let snapshot = GraphSnapshot::from_json_str(&snapshot_text).unwrap();

    let result = diff(&schema, &snapshot);
    assert!(!diff_has_errors(&result), "{result:?}");
}

#[test]
fn diff_detects_missing_label() {
    let ontology = load_ontology_from_path(example_path("manufacturing.native.yaml")).unwrap();
    let schema = GraphSchema::from_com(&ontology);

    let snapshot = GraphSnapshot {
        labels: vec!["Product".into()],
        relationship_types: vec![],
        node_properties: Default::default(),
    };

    let result = diff(&schema, &snapshot);
    assert!(diff_has_errors(&result));
    assert!(result.missing_labels.contains(&"Part".to_string()));
}
