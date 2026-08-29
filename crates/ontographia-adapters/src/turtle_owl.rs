use indexmap::IndexMap;
use ontographia_core::com::{
    CanonicalOntology, ClassDef, Datatype, PropertyDef, RelDef, RelDirection, SourceMetadata,
};
use ontographia_core::error::{OntographiaError, Result};
use rio_api::model::Term;
use rio_api::parser::TriplesParser;
use rio_turtle::{TurtleError, TurtleParser};

use crate::registry::OntologyAdapter;

const OWL_CLASS: &str = "http://www.w3.org/2002/07/owl#Class";
const OWL_OBJECT_PROPERTY: &str = "http://www.w3.org/2002/07/owl#ObjectProperty";
const OWL_DATATYPE_PROPERTY: &str = "http://www.w3.org/2002/07/owl#DatatypeProperty";
const RDF_TYPE: &str = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";
const RDFS_SUBCLASS_OF: &str = "http://www.w3.org/2000/01/rdf-schema#subClassOf";
const RDFS_DOMAIN: &str = "http://www.w3.org/2000/01/rdf-schema#domain";
const RDFS_RANGE: &str = "http://www.w3.org/2000/01/rdf-schema#range";

pub struct TurtleOwlAdapter;

impl OntologyAdapter for TurtleOwlAdapter {
    fn name(&self) -> &'static str {
        "turtle_owl"
    }

    fn detect(source: &[u8], path_hint: Option<&str>) -> bool {
        if path_hint.is_some_and(|p| {
            p.ends_with(".ttl") || p.ends_with(".turtle") || p.ends_with(".owl")
        }) {
            return true;
        }
        let text = String::from_utf8_lossy(source);
        text.contains("@prefix") || text.contains("owl:Class") || text.contains("a owl:Class")
    }

    fn parse(source: &[u8]) -> Result<CanonicalOntology> {
        let mut parser = TurtleParser::new(source, None);

        let prefixes: IndexMap<String, String> = IndexMap::new();
        let mut classes: IndexMap<String, ClassDef> = IndexMap::new();
        let mut object_props: IndexMap<String, (Option<String>, Option<String>)> = IndexMap::new();
        let mut datatype_props: IndexMap<String, Vec<String>> = IndexMap::new();
        let mut subclass_of: Vec<(String, String)> = Vec::new();
        let mut domains: IndexMap<String, Vec<String>> = IndexMap::new();
        let mut prop_kinds: IndexMap<String, String> = IndexMap::new();

        let mut on_triple = |triple: rio_api::model::Triple<'_>| -> std::result::Result<(), TurtleError> {
                let subject = subject_name(&triple.subject, &prefixes);
                let predicate = triple.predicate.iri;
                let object = local_name(&triple.object, &prefixes);

                if predicate == RDFS_SUBCLASS_OF {
                    subclass_of.push((subject.clone(), object.clone()));
                } else if predicate == RDFS_DOMAIN {
                    domains.entry(subject.clone()).or_default().push(object);
                } else if predicate == RDFS_RANGE {
                    object_props.entry(subject.clone()).or_default().1 = Some(object);
                } else if predicate == RDF_TYPE {
                    let object_iri = match &triple.object {
                        Term::NamedNode(n) => n.iri,
                        _ => "",
                    };
                    if object_iri == OWL_CLASS {
                        classes.entry(subject.clone()).or_insert(ClassDef {
                            name: subject,
                            iri: Some(triple.subject.to_string()),
                            super_classes: vec![],
                            description: None,
                        });
                    } else if object_iri == OWL_OBJECT_PROPERTY {
                        prop_kinds.insert(subject.clone(), "object".into());
                        object_props.entry(subject).or_default();
                    } else if object_iri == OWL_DATATYPE_PROPERTY {
                        prop_kinds.insert(subject.clone(), "datatype".into());
                    }
                }
                Ok(())
        };
        parser
            .parse_all(&mut on_triple)
            .map_err(|e| OntographiaError::Parse(e.to_string()))?;

        for (child, parent) in subclass_of {
            if let Some(class) = classes.get_mut(&child) {
                class.super_classes.push(parent);
            }
        }

        for (prop, domain_list) in domains {
            match prop_kinds.get(&prop).map(String::as_str) {
                Some("object") => {
                    if let Some(domain) = domain_list.into_iter().next() {
                        object_props.entry(prop).or_default().0 = Some(domain);
                    }
                }
                Some("datatype") => {
                    datatype_props.insert(prop, domain_list);
                }
                _ => {
                    if object_props.contains_key(&prop) {
                        if let Some(domain) = domain_list.into_iter().next() {
                            object_props.entry(prop).or_default().0 = Some(domain);
                        }
                    } else {
                        datatype_props.insert(prop, domain_list);
                    }
                }
            }
        }

        let relationships = object_props
            .into_iter()
            .map(|(name, (from, to))| RelDef {
                name,
                iri: None,
                from_class: from,
                to_class: to,
                direction: RelDirection::Out,
            })
            .collect();

        let properties = datatype_props
            .into_iter()
            .flat_map(|(name, owner_classes)| {
                owner_classes.into_iter().map(move |owner_class| PropertyDef {
                    name: name.clone(),
                    iri: None,
                    owner_class,
                    datatype: Datatype::String,
                    required: false,
                    unique: false,
                })
            })
            .collect();

        Ok(CanonicalOntology {
            classes: classes.into_values().collect(),
            relationships,
            properties,
            constraints: vec![],
            namespaces: prefixes,
            source: SourceMetadata {
                format: Some("turtle_owl".into()),
                uri: None,
                version: None,
            },
        })
    }

    fn supported_extensions() -> &'static [&'static str] {
        &[".ttl", ".turtle", ".owl"]
    }
}

fn subject_name(subject: &rio_api::model::Subject<'_>, prefixes: &IndexMap<String, String>) -> String {
    match subject {
        rio_api::model::Subject::NamedNode(node) => shorten_iri(node.iri, prefixes),
        rio_api::model::Subject::BlankNode(b) => format!("_:{}", b.id),
        rio_api::model::Subject::Triple(_) => "_:reified".to_string(),
    }
}

fn local_name(term: &Term<'_>, prefixes: &IndexMap<String, String>) -> String {
    match term {
        Term::NamedNode(node) => shorten_iri(node.iri, prefixes),
        Term::BlankNode(b) => format!("_:{}", b.id),
        Term::Literal(l) => l.to_string(),
        #[allow(unreachable_patterns)]
        _ => term.to_string(),
    }
}

fn shorten_iri(iri: &str, prefixes: &IndexMap<String, String>) -> String {
    for (prefix, ns) in prefixes {
        if let Some(local) = iri.strip_prefix(ns) {
            return format!("{}:{}", prefix, local);
        }
    }
    if let Some((_, local)) = iri.rsplit_once('#') {
        return local.to_string();
    }
    if let Some((_, local)) = iri.rsplit_once('/') {
        return local.to_string();
    }
    iri.to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_turtle_owl() {
        let ttl = include_str!("../../../examples/manufacturing.owl.ttl");
        let ont = TurtleOwlAdapter::parse(ttl.as_bytes()).unwrap();
        assert!(ont.classes.iter().any(|c| c.name == "Product"));
    }
}
