use ontographia_core::com::{CanonicalOntology, SourceMetadata};
use ontographia_core::error::{OntographiaError, Result};
use serde_json::Value;

use crate::registry::OntologyAdapter;
use crate::turtle_owl::TurtleOwlAdapter;

pub struct JsonLdAdapter;

impl OntologyAdapter for JsonLdAdapter {
    fn name(&self) -> &'static str {
        "jsonld"
    }

    fn detect(source: &[u8], path_hint: Option<&str>) -> bool {
        if path_hint.is_some_and(|p| p.ends_with(".jsonld") || p.ends_with(".json")) {
            if let Ok(v) = serde_json::from_slice::<Value>(source) {
                return v.get("@context").is_some() || v.get("@graph").is_some();
            }
        }
        false
    }

    fn parse(source: &[u8]) -> Result<CanonicalOntology> {
        let value: Value = serde_json::from_slice(source)?;
        let ttl = jsonld_to_turtle(&value)?;
        let mut ont = TurtleOwlAdapter::parse(ttl.as_bytes())?;
        ont.source = SourceMetadata {
            format: Some("jsonld".into()),
            uri: value
                .get("@id")
                .and_then(|v| v.as_str())
                .map(String::from),
            version: None,
        };
        Ok(ont)
    }

    fn supported_extensions() -> &'static [&'static str] {
        &[".jsonld"]
    }
}

fn jsonld_to_turtle(value: &Value) -> Result<String> {
    let context = value.get("@context").cloned().unwrap_or(Value::Null);
    let mut prefix_lines = vec![
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .".into(),
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .".into(),
    ];
    let mut prefixes = indexmap::IndexMap::new();

    if let Value::Object(ctx) = context {
        for (key, val) in ctx {
            if let Some(uri) = val.as_str() {
                prefixes.insert(key.clone(), uri.to_string());
                prefix_lines.push(format!("@prefix {key}: <{uri}> ."));
            }
        }
    }

    let mut lines = prefix_lines;

    let nodes: Vec<&Value> = if let Some(graph) = value.get("@graph").and_then(|g| g.as_array()) {
        graph.iter().collect()
    } else if value.is_array() {
        value.as_array().unwrap().iter().collect()
    } else {
        vec![value]
    };

    for node in nodes {
        let id = node
            .get("@id")
            .and_then(|v| v.as_str())
            .ok_or_else(|| OntographiaError::Parse("JSON-LD node missing @id".into()))?;
        let iri = expand_id(id, &prefixes);

        let types = node
            .get("@type")
            .map(|t| {
                if let Some(arr) = t.as_array() {
                    arr.iter()
                        .filter_map(|v| v.as_str())
                        .map(String::from)
                        .collect::<Vec<_>>()
                } else {
                    t.as_str().map(|s| vec![s.to_string()]).unwrap_or_default()
                }
            })
            .unwrap_or_default();

        for ty in types {
            if ty == "owl:Class" || ty.ends_with("Class") {
                lines.push(format!("<{iri}> a owl:Class ."));
            } else if ty == "owl:ObjectProperty" || ty.ends_with("ObjectProperty") {
                lines.push(format!("<{iri}> a owl:ObjectProperty ."));
            } else if ty == "owl:DatatypeProperty" || ty.ends_with("DatatypeProperty") {
                lines.push(format!("<{iri}> a owl:DatatypeProperty ."));
            }
        }

        for (key, val) in node.as_object().into_iter().flatten() {
            if key.starts_with('@') {
                continue;
            }
            let predicate = if key.contains(':') {
                let (pfx, local) = key.split_once(':').unwrap();
                let ns = prefixes
                    .get(pfx)
                    .ok_or_else(|| OntographiaError::Parse(format!("unknown prefix: {pfx}")))?;
                format!("{ns}{local}")
            } else {
                key.clone()
            };

            let object_iri = jsonld_ref_to_iri(val, &prefixes)?;
            if predicate.ends_with("subClassOf") {
                lines.push(format!("<{iri}> rdfs:subClassOf <{object_iri}> ."));
            } else if predicate.ends_with("domain") {
                for domain_iri in jsonld_ref_to_iris(val, &prefixes)? {
                    lines.push(format!("<{iri}> rdfs:domain <{domain_iri}> ."));
                }
            } else if predicate.ends_with("range") {
                for range_iri in jsonld_ref_to_iris(val, &prefixes)? {
                    lines.push(format!("<{iri}> rdfs:range <{range_iri}> ."));
                }
            }
        }
    }

    Ok(lines.join("\n"))
}

fn expand_id(id: &str, prefixes: &indexmap::IndexMap<String, String>) -> String {
    if id.starts_with("http://") || id.starts_with("https://") {
        return id.to_string();
    }
    if let Some((pfx, local)) = id.split_once(':') {
        if let Some(ns) = prefixes.get(pfx) {
            return format!("{ns}{local}");
        }
    }
    id.to_string()
}

fn jsonld_ref_to_iri(value: &Value, prefixes: &indexmap::IndexMap<String, String>) -> Result<String> {
    jsonld_ref_to_iris(value, prefixes)?
        .into_iter()
        .next()
        .ok_or_else(|| OntographiaError::Parse("unsupported JSON-LD value".into()))
}

fn jsonld_ref_to_iris(value: &Value, prefixes: &indexmap::IndexMap<String, String>) -> Result<Vec<String>> {
    if let Some(arr) = value.as_array() {
        let mut out = Vec::new();
        for item in arr {
            out.extend(jsonld_ref_to_iris(item, prefixes)?);
        }
        return Ok(out);
    }
    if let Some(id) = value.get("@id").and_then(|v| v.as_str()) {
        return Ok(vec![expand_id(id, prefixes)]);
    }
    if let Some(s) = value.as_str() {
        return Ok(vec![expand_id(s, prefixes)]);
    }
    Err(OntographiaError::Parse("unsupported JSON-LD value".into()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_jsonld() {
        let json = include_str!("../../../examples/manufacturing.jsonld");
        let ont = JsonLdAdapter::parse(json.as_bytes()).unwrap();
        assert!(ont.classes.iter().any(|c| c.name == "Product"));
        assert!(ont.resolve_property("Part", "part_number").is_some());
    }
}
