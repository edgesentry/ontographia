use indexmap::IndexMap;
use ontographia_core::com::{
    CanonicalOntology, ClassDef, Datatype, PropertyDef, RelDef, RelDirection, SourceMetadata,
};
use ontographia_core::error::Result;
use serde::Deserialize;

use crate::registry::OntologyAdapter;

#[derive(Debug, Deserialize)]
#[allow(dead_code)]
struct LinkMlSchema {
    #[serde(default)]
    id: Option<String>,
    #[serde(default)]
    name: Option<String>,
    #[serde(default)]
    prefixes: IndexMap<String, String>,
    #[serde(default)]
    default_range: Option<String>,
    classes: IndexMap<String, LinkMlClass>,
    #[serde(default)]
    slots: IndexMap<String, LinkMlSlot>,
}

#[derive(Debug, Deserialize)]
struct LinkMlClass {
    #[serde(default)]
    is_a: Option<String>,
    #[serde(default)]
    slots: Vec<String>,
    #[serde(default)]
    description: Option<String>,
}

#[derive(Debug, Deserialize)]
#[allow(dead_code)]
struct LinkMlSlot {
    #[serde(default)]
    range: Option<String>,
    #[serde(default)]
    required: Option<bool>,
    #[serde(default)]
    multivalued: Option<bool>,
    #[serde(default)]
    slot_uri: Option<String>,
}

pub struct LinkMlAdapter;

impl OntologyAdapter for LinkMlAdapter {
    fn name(&self) -> &'static str {
        "linkml"
    }

    fn detect(source: &[u8], path_hint: Option<&str>) -> bool {
        if path_hint.is_some_and(|p| p.ends_with(".linkml.yaml") || p.ends_with(".linkml.yml")) {
            return true;
        }
        let text = String::from_utf8_lossy(source);
        text.contains("linkml_version:") || (text.contains("classes:") && text.contains("slots:"))
    }

    fn parse(source: &[u8]) -> Result<CanonicalOntology> {
        let schema: LinkMlSchema = serde_yaml::from_slice(source)?;
        let mut classes = Vec::new();
        let mut properties = Vec::new();
        let mut relationships = Vec::new();

        for (name, class) in &schema.classes {
            classes.push(ClassDef {
                name: name.clone(),
                iri: schema.prefixes.get("linkml").map(|_| name.clone()),
                super_classes: class.is_a.clone().into_iter().collect(),
                description: class.description.clone(),
            });

            for slot_name in &class.slots {
                if let Some(slot) = schema.slots.get(slot_name) {
                    if let Some(range) = &slot.range {
                        if schema.classes.contains_key(range) {
                            relationships.push(RelDef {
                                name: slot_name.clone(),
                                iri: slot.slot_uri.clone(),
                                from_class: Some(name.clone()),
                                to_class: Some(range.clone()),
                                direction: RelDirection::Out,
                            });
                        } else {
                            properties.push(PropertyDef {
                                name: slot_name.clone(),
                                iri: slot.slot_uri.clone(),
                                owner_class: name.clone(),
                                datatype: linkml_range_to_datatype(range),
                                required: slot.required.unwrap_or(false),
                            });
                        }
                    }
                }
            }
        }

        Ok(CanonicalOntology {
            classes,
            relationships,
            properties,
            constraints: vec![],
            namespaces: schema.prefixes,
            source: SourceMetadata {
                format: Some("linkml".into()),
                uri: schema.id,
                version: schema.name,
            },
        })
    }

    fn supported_extensions() -> &'static [&'static str] {
        &[".linkml.yaml", ".linkml.yml"]
    }
}

fn linkml_range_to_datatype(range: &str) -> Datatype {
    match range {
        "integer" | "int" => Datatype::Integer,
        "float" | "double" | "decimal" => Datatype::Float,
        "boolean" | "bool" => Datatype::Boolean,
        "date" => Datatype::Date,
        "datetime" => Datatype::DateTime,
        "uri" | "curie" | "ncname" => Datatype::Iri,
        _ => Datatype::String,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_linkml() {
        let yaml = include_str!("../../../examples/manufacturing.linkml.yaml");
        let ont = LinkMlAdapter::parse(yaml.as_bytes()).unwrap();
        assert!(ont.classes.iter().any(|c| c.name == "Product"));
    }
}
