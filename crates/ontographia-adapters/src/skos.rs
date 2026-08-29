use ontographia_core::com::{
    CanonicalOntology, ClassDef, RelDef, RelDirection, SourceMetadata,
};
use ontographia_core::error::Result;

use crate::registry::OntologyAdapter;
use crate::turtle_owl::TurtleOwlAdapter;

pub struct SkosAdapter;

impl OntologyAdapter for SkosAdapter {
    fn name(&self) -> &'static str {
        "skos"
    }

    fn detect(source: &[u8], path_hint: Option<&str>) -> bool {
        if path_hint.is_some_and(|p| p.ends_with(".skos.ttl")) {
            return true;
        }
        let text = String::from_utf8_lossy(source);
        text.contains("skos:Concept") || text.contains("skos:broader")
    }

    fn parse(source: &[u8]) -> Result<CanonicalOntology> {
        let mut ont = TurtleOwlAdapter::parse(source)?;
        if ont.classes.is_empty() {
            ont.classes.push(ClassDef {
                name: "Concept".into(),
                iri: Some("http://www.w3.org/2004/02/skos/core#Concept".into()),
                super_classes: vec![],
                description: Some("SKOS Concept".into()),
            });
        }
        let skos_rels = [
            ("broader", "skos:broader"),
            ("narrower", "skos:narrower"),
            ("related", "skos:related"),
        ];
        for (name, iri) in skos_rels {
            if !ont.relationships.iter().any(|r| r.name == name) {
                ont.relationships.push(RelDef {
                    name: name.into(),
                    iri: Some(format!("http://www.w3.org/2004/02/skos/core#{iri}")),
                    from_class: Some("Concept".into()),
                    to_class: Some("Concept".into()),
                    direction: RelDirection::Out,
                });
            }
        }
        ont.source = SourceMetadata {
            format: Some("skos".into()),
            uri: None,
            version: None,
        };
        Ok(ont)
    }

    fn supported_extensions() -> &'static [&'static str] {
        &[".skos.ttl"]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_skos() {
        let ttl = r#"
@prefix ex: <http://example.org/> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
ex:Thing a owl:Class .
"#;
        let ont = SkosAdapter::parse(ttl.as_bytes()).unwrap();
        assert!(ont.relationships.iter().any(|r| r.name == "broader"));
    }
}
