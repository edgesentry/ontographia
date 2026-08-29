use ontographia_adapters::load_ontology_from_path;
use ontographia_core::emit::Dialect;
use ontographia_core::engine::Engine;
use ontographia_core::intent::{
    Direction, FilterExpr, FilterOp, Intent, NodeRef, ReturnItem, TraverseStep,
};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let path = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "examples/manufacturing.native.yaml".to_string());

    let ontology = load_ontology_from_path(&path)?;
    let engine = Engine::new(ontology);

    // BOM + supply chain: suppliers for parts in product SPX-100
    let intent = Intent {
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
    };

    let emitted = engine.build(intent, Dialect::Cypher25)?;
    println!("{}", emitted.query);
    println!("params: {:?}", emitted.params);
    Ok(())
}
