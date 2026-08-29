use indexmap::IndexMap;
use ontographia_core::com::{
    CanonicalOntology, ClassDef, Datatype, PropertyDef, RelDef, RelDirection, SourceMetadata,
};
use ontographia_core::error::{OntographiaError, Result};
use serde::Deserialize;

use crate::registry::OntologyAdapter;

#[derive(Debug, Deserialize)]
struct NativeOntology {
    #[serde(default)]
    namespaces: IndexMap<String, String>,
    classes: Vec<NativeClass>,
    #[serde(default)]
    relationships: Vec<NativeRel>,
    #[serde(default)]
    properties: Vec<NativeProp>,
}

#[derive(Debug, Deserialize)]
struct NativeClass {
    name: String,
    #[serde(default)]
    super_classes: Vec<String>,
    #[serde(default)]
    description: Option<String>,
}

#[derive(Debug, Deserialize)]
struct NativeRel {
    name: String,
    #[serde(default)]
    from_class: Option<String>,
    #[serde(default)]
    to_class: Option<String>,
    #[serde(default)]
    direction: Option<String>,
}

#[derive(Debug, Deserialize)]
struct NativeProp {
    name: String,
    owner_class: String,
    #[serde(default)]
    datatype: Option<String>,
    #[serde(default)]
    required: bool,
}

pub struct NativeYamlAdapter;

impl OntologyAdapter for NativeYamlAdapter {
    fn name(&self) -> &'static str {
        "native_yaml"
    }

    fn detect(source: &[u8], path_hint: Option<&str>) -> bool {
        if path_hint.is_some_and(|p| {
            p.ends_with(".native.yaml")
                || p.ends_with(".ontographia.yaml")
                || p.ends_with(".ont.yaml")
        }) {
            return true;
        }
        let trimmed = source.iter().take(512).copied().collect::<Vec<_>>();
        let text = String::from_utf8_lossy(&trimmed);
        text.contains("classes:") && !text.contains("linkml_version:")
    }

    fn parse(source: &[u8]) -> Result<CanonicalOntology> {
        let raw: NativeOntology = serde_yaml::from_slice(source)?;
        Ok(CanonicalOntology {
            namespaces: raw.namespaces,
            classes: raw
                .classes
                .into_iter()
                .map(|c| ClassDef {
                    name: c.name,
                    iri: None,
                    super_classes: c.super_classes,
                    description: c.description,
                })
                .collect(),
            relationships: raw
                .relationships
                .into_iter()
                .map(|r| RelDef {
                    name: r.name,
                    iri: None,
                    from_class: r.from_class,
                    to_class: r.to_class,
                    direction: match r.direction.as_deref() {
                        Some("in") => RelDirection::In,
                        Some("both") => RelDirection::Both,
                        _ => RelDirection::Out,
                    },
                })
                .collect(),
            properties: raw
                .properties
                .into_iter()
                .map(|p| PropertyDef {
                    name: p.name,
                    iri: None,
                    owner_class: p.owner_class,
                    datatype: parse_datatype(p.datatype.as_deref()),
                    required: p.required,
                })
                .collect(),
            constraints: vec![],
            source: SourceMetadata {
                format: Some("native_yaml".into()),
                uri: None,
                version: None,
            },
        })
    }

    fn supported_extensions() -> &'static [&'static str] {
        &[".native.yaml", ".ontographia.yaml", ".ont.yaml"]
    }
}

fn parse_datatype(value: Option<&str>) -> Datatype {
    match value.unwrap_or("string").to_lowercase().as_str() {
        "integer" | "int" => Datatype::Integer,
        "float" | "double" | "decimal" => Datatype::Float,
        "boolean" | "bool" => Datatype::Boolean,
        "date" => Datatype::Date,
        "datetime" | "date_time" => Datatype::DateTime,
        "iri" | "uri" => Datatype::Iri,
        _ => Datatype::String,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_native_yaml() {
        let yaml = include_str!("../../../examples/manufacturing.native.yaml");
        let ont = NativeYamlAdapter::parse(yaml.as_bytes()).unwrap();
        assert_eq!(ont.classes[0].name, "Product");
    }
}
