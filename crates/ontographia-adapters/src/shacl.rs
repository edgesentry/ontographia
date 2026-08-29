use ontographia_core::com::{CanonicalOntology, Constraint, ConstraintKind, SourceMetadata};
use ontographia_core::error::Result;

use crate::registry::OntologyAdapter;
use crate::turtle_owl::TurtleOwlAdapter;

pub struct ShaclAdapter;

impl OntologyAdapter for ShaclAdapter {
    fn name(&self) -> &'static str {
        "shacl"
    }

    fn detect(source: &[u8], path_hint: Option<&str>) -> bool {
        if path_hint.is_some_and(|p| p.ends_with(".shacl.ttl") || p.contains("shacl")) {
            return true;
        }
        let text = String::from_utf8_lossy(source);
        text.contains("sh:NodeShape") || text.contains("sh:PropertyShape")
    }

    fn parse(source: &[u8]) -> Result<CanonicalOntology> {
        let mut ont = TurtleOwlAdapter::parse(source)?;
        ont.constraints.extend(extract_shacl_constraints(source)?);
        ont.source.format = Some("shacl".into());
        Ok(ont)
    }

    fn supported_extensions() -> &'static [&'static str] {
        &[".shacl.ttl"]
    }
}

fn extract_shacl_constraints(source: &[u8]) -> Result<Vec<Constraint>> {
    let text = String::from_utf8_lossy(source);
    let mut constraints = Vec::new();

    for line in text.lines() {
        let line = line.trim();
        if line.contains("sh:targetClass") {
            if let Some(target) = extract_iri_local(line, "sh:targetClass") {
                constraints.push(Constraint {
                    kind: ConstraintKind::MinCount,
                    target_class: target,
                    property: None,
                    value: Some(serde_json::json!(1)),
                });
            }
        }
        if line.contains("sh:datatype") {
            if let (Some(target), Some(prop)) = (
                extract_shape_target(&text),
                extract_property_path(line),
            ) {
                constraints.push(Constraint {
                    kind: ConstraintKind::Datatype,
                    target_class: target,
                    property: Some(prop),
                    value: extract_literal_after(line, "sh:datatype"),
                });
            }
        }
        if line.contains("sh:pattern") {
            if let (Some(target), Some(prop)) = (
                extract_shape_target(&text),
                extract_property_path(line),
            ) {
                constraints.push(Constraint {
                    kind: ConstraintKind::Pattern,
                    target_class: target,
                    property: Some(prop),
                    value: extract_literal_after(line, "sh:pattern"),
                });
            }
        }
    }

    Ok(constraints)
}

fn extract_iri_local(line: &str, key: &str) -> Option<String> {
    line.split(key).nth(1).map(|rest| {
        rest.trim()
            .trim_matches(|c| c == '.' || c == ';')
            .trim()
            .trim_start_matches('<')
            .trim_end_matches('>')
            .rsplit_once('#')
            .map(|(_, local)| local.to_string())
            .unwrap_or_else(|| rest.trim().to_string())
    })
}

fn extract_shape_target(text: &str) -> Option<String> {
    text.lines()
        .find(|l| l.contains("sh:targetClass"))
        .and_then(|l| extract_iri_local(l, "sh:targetClass"))
}

fn extract_property_path(line: &str) -> Option<String> {
    line.split("sh:path").nth(1).map(|rest| {
        rest.trim()
            .trim_matches(|c| c == '.' || c == ';')
            .trim()
            .trim_start_matches('<')
            .trim_end_matches('>')
            .rsplit('/')
            .next_back()
            .unwrap_or("")
            .to_string()
    })
}

fn extract_literal_after(line: &str, key: &str) -> Option<serde_json::Value> {
    line.split(key).nth(1).map(|rest| {
        let lit = rest
            .trim()
            .trim_matches(|c| c == '.' || c == ';')
            .trim()
            .trim_matches('"');
        serde_json::Value::String(lit.to_string())
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detects_shacl() {
        let ttl = "@prefix sh: <http://www.w3.org/ns/shacl#> .\n_:shape a sh:NodeShape ; sh:targetClass ex:Person .";
        assert!(ShaclAdapter::detect(ttl.as_bytes(), Some("shape.shacl.ttl")));
    }
}
