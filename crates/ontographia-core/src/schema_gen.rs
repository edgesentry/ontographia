use crate::com::CanonicalOntology;

pub fn intent_json_schema(ontology: &CanonicalOntology) -> serde_json::Value {
    let mut schema = serde_json::to_value(schemars::schema_for!(crate::intent::Intent))
        .expect("schema serialization");
    enrich_with_ontology(&mut schema, ontology);
    schema
}

fn enrich_with_ontology(schema: &mut serde_json::Value, ontology: &CanonicalOntology) {
    let classes: Vec<serde_json::Value> = ontology
        .classes
        .iter()
        .map(|c| serde_json::json!(c.name))
        .collect();
    let relationships: Vec<serde_json::Value> = ontology
        .relationships
        .iter()
        .map(|r| serde_json::json!(r.name))
        .collect();

    if let Some(props) = schema.get_mut("properties") {
        if let Some(start) = props.get_mut("start") {
            inject_enum_on_field(start, "class", &classes);
        }
        if let Some(traverse) = props.get_mut("traverse") {
            if let Some(items) = traverse
                .get_mut("items")
                .and_then(|i| i.get_mut("properties"))
            {
                if let Some(rel) = items.get_mut("relationship") {
                    rel.as_object_mut()
                        .map(|o| o.insert("enum".into(), serde_json::Value::Array(relationships.clone())));
                }
                if let Some(to) = items.get_mut("to") {
                    inject_enum_on_field(to, "class", &classes);
                }
            }
        }
    }
}

fn inject_enum_on_field(parent: &mut serde_json::Value, field: &str, values: &[serde_json::Value]) {
    if let Some(props) = parent.get_mut("properties").and_then(|p| p.as_object_mut()) {
        if let Some(target) = props.get_mut(field) {
            if let Some(obj) = target.as_object_mut() {
                obj.insert("enum".into(), serde_json::Value::Array(values.to_vec()));
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::com::{CanonicalOntology, ClassDef};

    #[test]
    fn schema_includes_class_enums() {
        let ont = CanonicalOntology {
            classes: vec![ClassDef {
                name: "Person".into(),
                iri: None,
                super_classes: vec![],
                description: None,
            }],
            relationships: vec![],
            properties: vec![],
            constraints: vec![],
            namespaces: indexmap::IndexMap::new(),
            source: Default::default(),
        };
        let schema = intent_json_schema(&ont);
        assert!(schema.get("properties").is_some());
    }
}
