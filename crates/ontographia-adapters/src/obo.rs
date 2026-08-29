use ontographia_core::com::{
    CanonicalOntology, ClassDef, Datatype, PropertyDef, RelDef, RelDirection, SourceMetadata,
};
use ontographia_core::error::{OntographiaError, Result};

use crate::registry::OntologyAdapter;

pub struct OboAdapter;

impl OntologyAdapter for OboAdapter {
    fn name(&self) -> &'static str {
        "obo"
    }

    fn detect(source: &[u8], path_hint: Option<&str>) -> bool {
        if path_hint.is_some_and(|p| p.ends_with(".obo")) {
            return true;
        }
        let text = String::from_utf8_lossy(source);
        text.starts_with("format-version:") || text.contains("[Term]")
    }

    fn parse(source: &[u8]) -> Result<CanonicalOntology> {
        let text = std::str::from_utf8(source)
            .map_err(|e| OntographiaError::Parse(e.to_string()))?;
        let mut classes = Vec::new();
        let mut relationships = Vec::new();
        let mut properties = Vec::new();
        let mut current_id: Option<String> = None;
        let mut current_name: Option<String> = None;
        let mut current_is_a: Vec<String> = Vec::new();
        let mut current_rels: Vec<(String, String)> = Vec::new();

        let flush = |id: &Option<String>,
                     name: &Option<String>,
                     is_a: &Vec<String>,
                     rels: &Vec<(String, String)>,
                     classes: &mut Vec<ClassDef>,
                     relationships: &mut Vec<RelDef>,
                     properties: &mut Vec<PropertyDef>| {
            if let Some(id) = id {
                let class_name = name.clone().unwrap_or_else(|| id.clone());
                classes.push(ClassDef {
                    name: class_name.clone(),
                    iri: Some(id.clone()),
                    super_classes: is_a.clone(),
                    description: None,
                });
                properties.push(PropertyDef {
                    name: "label".into(),
                    iri: None,
                    owner_class: class_name.clone(),
                    datatype: Datatype::String,
                    required: true,
                    unique: false,
                });
                for (rel_type, target) in rels {
                    relationships.push(RelDef {
                        name: rel_type.clone(),
                        iri: None,
                        from_class: Some(class_name.clone()),
                        to_class: Some(target.clone()),
                        direction: RelDirection::Out,
                    });
                }
            }
        };

        for line in text.lines() {
            let line = line.trim();
            if line == "[Term]" {
                flush(
                    &current_id,
                    &current_name,
                    &current_is_a,
                    &current_rels,
                    &mut classes,
                    &mut relationships,
                    &mut properties,
                );
                current_id = None;
                current_name = None;
                current_is_a.clear();
                current_rels.clear();
            } else if let Some(id) = line.strip_prefix("id: ") {
                current_id = Some(id.trim().to_string());
            } else if let Some(name) = line.strip_prefix("name: ") {
                current_name = Some(name.trim().to_string());
            } else if let Some(parent) = line.strip_prefix("is_a: ") {
                let parent = parent.split('!').next().unwrap_or(parent).trim();
                current_is_a.push(parent.to_string());
            } else if let Some(rel) = line.strip_prefix("relationship: ") {
                let mut parts = rel.split_whitespace();
                if let (Some(rel_type), Some(target)) = (parts.next(), parts.next()) {
                    let target = target.split('!').next().unwrap_or(target);
                    current_rels.push((rel_type.to_string(), target.to_string()));
                }
            }
        }
        flush(
            &current_id,
            &current_name,
            &current_is_a,
            &current_rels,
            &mut classes,
            &mut relationships,
            &mut properties,
        );

        Ok(CanonicalOntology {
            classes,
            relationships,
            properties,
            constraints: vec![],
            namespaces: indexmap::IndexMap::new(),
            source: SourceMetadata {
                format: Some("obo".into()),
                uri: None,
                version: None,
            },
        })
    }

    fn supported_extensions() -> &'static [&'static str] {
        &[".obo"]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_obo() {
        let obo = include_str!("../../../examples/manufacturing.obo");
        let ont = OboAdapter::parse(obo.as_bytes()).unwrap();
        assert!(!ont.classes.is_empty());
    }
}
