use crate::model::GraphSchema;

/// Serialize the derived graph schema as pretty-printed JSON.
pub fn emit_schema_json(schema: &GraphSchema) -> crate::error::Result<String> {
    Ok(serde_json::to_string_pretty(schema)?)
}

/// Emit Neo4j Cypher 25 `CREATE CONSTRAINT` statements for all `unique` properties in the schema.
pub fn emit_cypher25_constraints(schema: &GraphSchema) -> String {
    let mut statements = Vec::new();

    for (label, label_schema) in &schema.labels {
        for property in &label_schema.unique_properties {
            let constraint_name = constraint_name(label, property);
            statements.push(format!(
                "CYPHER 25\nCREATE CONSTRAINT {constraint_name} IF NOT EXISTS\nFOR (n:{label}) REQUIRE n.{property} IS UNIQUE;"
            ));
        }
    }

    statements.join("\n\n")
}

fn constraint_name(label: &str, property: &str) -> String {
    format!("{}_{}", to_snake_case(label), to_snake_case(property))
}

fn to_snake_case(value: &str) -> String {
    let mut out = String::new();
    for (i, ch) in value.chars().enumerate() {
        if ch.is_uppercase() {
            if i > 0 {
                out.push('_');
            }
            out.push(ch.to_ascii_lowercase());
        } else if ch == '-' || ch == ' ' {
            out.push('_');
        } else {
            out.push(ch);
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::{GraphSchema, LabelSchema};
    use indexmap::IndexMap;
    use ontographia_core::com::Datatype;

    #[test]
    fn constraint_name_is_snake_case() {
        assert_eq!(constraint_name("Product", "sku"), "product_sku");
        assert_eq!(constraint_name("DefectType", "code"), "defect_type_code");
    }

    #[test]
    fn emits_unique_constraints() {
        let mut labels = IndexMap::new();
        labels.insert(
            "Product".into(),
            LabelSchema {
                properties: IndexMap::from([("sku".into(), Datatype::String)]),
                unique_properties: vec!["sku".into()],
            },
        );

        let schema = GraphSchema {
            labels,
            relationship_types: IndexMap::new(),
        };

        let cypher = emit_cypher25_constraints(&schema);
        assert!(cypher.contains("CREATE CONSTRAINT product_sku IF NOT EXISTS"));
        assert!(cypher.contains("FOR (n:Product) REQUIRE n.sku IS UNIQUE"));
    }

    #[test]
    fn emits_schema_json() {
        let mut labels = IndexMap::new();
        labels.insert(
            "Product".into(),
            LabelSchema {
                properties: IndexMap::from([("sku".into(), Datatype::String)]),
                unique_properties: vec!["sku".into()],
            },
        );
        let schema = GraphSchema {
            labels,
            relationship_types: IndexMap::new(),
        };
        let json = emit_schema_json(&schema).unwrap();
        assert!(json.contains("\"Product\""));
        assert!(json.contains("\"sku\""));
    }
}
