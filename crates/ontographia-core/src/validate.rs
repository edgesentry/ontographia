use crate::ast::{
    FilterNode, MatchClause, NodePattern, PatternNode, QueryAst, RelPattern, ReturnExpr, ReturnNode,
};
use crate::com::CanonicalOntology;
use crate::error::{OntographiaError, Result};
use crate::intent::{Intent, ReturnItem};
use indexmap::IndexMap;

#[derive(Debug, Clone)]
pub struct ValidatedIntent {
    pub intent: Intent,
    pub params: IndexMap<String, serde_json::Value>,
}

pub fn build_ast(_ontology: &CanonicalOntology, validated: &ValidatedIntent) -> Result<QueryAst> {
    let intent = &validated.intent;
    let mut nodes = vec![NodePattern {
        alias: intent.start.alias.clone(),
        labels: vec![intent.start.class.clone()],
    }];
    let mut relationships = Vec::new();

    for step in &intent.traverse {
        relationships.push(RelPattern {
            alias: None,
            rel_type: step.relationship.clone(),
            direction: step.direction,
            min_hops: step.min_hops,
            max_hops: step.max_hops,
        });
        nodes.push(NodePattern {
            alias: step.to.alias.clone(),
            labels: vec![step.to.class.clone()],
        });
    }

    let filters: Vec<FilterNode> = intent
        .filter
        .iter()
        .enumerate()
        .map(|(i, f)| FilterNode {
            alias: f.alias.clone(),
            property: f.property.clone(),
            op: f.op,
            param_name: format!("param_{}", i),
        })
        .collect();

    let returns: Vec<ReturnNode> = intent
        .r#return
        .iter()
        .map(map_return_item)
        .collect();

    let order_by = intent.order_by.as_ref().map(|o| crate::ast::OrderByNode {
        alias: o.alias.clone(),
        property: o.property.clone(),
        descending: o.descending,
    });

    Ok(QueryAst {
        match_clause: MatchClause {
            optional: intent.optional,
            patterns: vec![PatternNode {
                nodes,
                relationships,
            }],
        },
        filters,
        returns,
        order_by,
        limit: intent.limit,
        skip: intent.skip,
    })
}

fn map_return_item(item: &ReturnItem) -> ReturnNode {
    let expr = if let Some(agg) = item.aggregate {
        ReturnExpr::Aggregate {
            func: agg,
            alias: item.alias.clone(),
            property: item.property.clone(),
        }
    } else if let Some(prop) = &item.property {
        ReturnExpr::Property {
            alias: item.alias.clone(),
            property: prop.clone(),
        }
    } else {
        ReturnExpr::Node {
            alias: item.alias.clone(),
        }
    };

    ReturnNode {
        expr,
        alias: item.as_name.clone(),
    }
}

pub fn validate_intent(ontology: &CanonicalOntology, intent: Intent) -> Result<ValidatedIntent> {
    if ontology.resolve_class(&intent.start.class).is_none() {
        return Err(OntographiaError::Validation(format!(
            "unknown class: {}",
            intent.start.class
        )));
    }

    let mut aliases = vec![intent.start.alias.clone()];
    let mut prev_class = intent.start.class.clone();

    for step in &intent.traverse {
        if aliases.contains(&step.to.alias) {
            return Err(OntographiaError::Validation(format!(
                "duplicate alias: {}",
                step.to.alias
            )));
        }
        aliases.push(step.to.alias.clone());

        let rel = ontology
            .resolve_relationship(&step.relationship)
            .ok_or_else(|| {
                OntographiaError::Validation(format!(
                    "unknown relationship: {}",
                    step.relationship
                ))
            })?;

        if let Some(from) = &rel.from_class {
            if !ontology.is_subclass_of(&prev_class, from) && prev_class != *from {
                return Err(OntographiaError::Validation(format!(
                    "relationship '{}' does not originate from class '{}'",
                    step.relationship, prev_class
                )));
            }
        }
        if ontology.resolve_class(&step.to.class).is_none() {
            return Err(OntographiaError::Validation(format!(
                "unknown class: {}",
                step.to.class
            )));
        }
        if let Some(to) = &rel.to_class {
            if !ontology.is_subclass_of(&step.to.class, to) && step.to.class != *to {
                return Err(OntographiaError::Validation(format!(
                    "relationship '{}' does not target class '{}'",
                    step.relationship, step.to.class
                )));
            }
        }
        prev_class = step.to.class.clone();
    }

    for f in &intent.filter {
        if !aliases.contains(&f.alias) {
            return Err(OntographiaError::Validation(format!(
                "filter alias not in pattern: {}",
                f.alias
            )));
        }
        let class = find_class_for_alias(&intent, &f.alias)?;
        ontology
            .resolve_property(&class, &f.property)
            .ok_or_else(|| {
                OntographiaError::Validation(format!(
                    "unknown property '{}' on class '{}'",
                    f.property, class
                ))
            })?;
    }

    if intent.r#return.is_empty() {
        return Err(OntographiaError::Validation(
            "return clause must not be empty".into(),
        ));
    }

    for r in &intent.r#return {
        if !aliases.contains(&r.alias) {
            return Err(OntographiaError::Validation(format!(
                "return alias not in pattern: {}",
                r.alias
            )));
        }
        if let Some(prop) = &r.property {
            let class = find_class_for_alias(&intent, &r.alias)?;
            ontology
                .resolve_property(&class, prop)
                .ok_or_else(|| {
                    OntographiaError::Validation(format!(
                        "unknown property '{}' on class '{}'",
                        prop, class
                    ))
                })?;
        }
    }

    let mut params = IndexMap::new();
    for (i, f) in intent.filter.iter().enumerate() {
        params.insert(format!("param_{}", i), f.value.clone());
    }

    Ok(ValidatedIntent { intent, params })
}

fn find_class_for_alias(intent: &Intent, alias: &str) -> Result<String> {
    if intent.start.alias == alias {
        return Ok(intent.start.class.clone());
    }
    for step in &intent.traverse {
        if step.to.alias == alias {
            return Ok(step.to.class.clone());
        }
    }
    Err(OntographiaError::Validation(format!(
        "alias not found: {}",
        alias
    )))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::com::{CanonicalOntology, ClassDef, Datatype, PropertyDef, RelDef};
    use crate::intent::{FilterExpr, FilterOp, NodeRef, ReturnItem, TraverseStep};
    use crate::intent::Direction;

    fn sample_ontology() -> CanonicalOntology {
        CanonicalOntology {
            classes: vec![ClassDef {
                name: "Person".into(),
                iri: None,
                super_classes: vec![],
                description: None,
            }],
            relationships: vec![RelDef {
                name: "knows".into(),
                iri: None,
                from_class: Some("Person".into()),
                to_class: Some("Person".into()),
                direction: crate::com::RelDirection::Out,
            }],
            properties: vec![
                PropertyDef {
                    name: "name".into(),
                    iri: None,
                    owner_class: "Person".into(),
                    datatype: Datatype::String,
                    required: true,
                },
                PropertyDef {
                    name: "age".into(),
                    iri: None,
                    owner_class: "Person".into(),
                    datatype: Datatype::Integer,
                    required: false,
                },
            ],
            constraints: vec![],
            namespaces: indexmap::IndexMap::new(),
            source: Default::default(),
        }
    }

    fn sample_intent() -> Intent {
        Intent {
            start: NodeRef {
                class: "Person".into(),
                alias: "p".into(),
            },
            traverse: vec![TraverseStep {
                relationship: "knows".into(),
                direction: Direction::Out,
                to: NodeRef {
                    class: "Person".into(),
                    alias: "friend".into(),
                },
                min_hops: None,
                max_hops: None,
            }],
            filter: vec![FilterExpr {
                alias: "p".into(),
                property: "age".into(),
                op: FilterOp::Gte,
                value: serde_json::json!(30),
            }],
            r#return: vec![ReturnItem {
                alias: "friend".into(),
                property: Some("name".into()),
                aggregate: None,
                as_name: Some("name".into()),
            }],
            order_by: None,
            limit: Some(10),
            skip: None,
            optional: false,
        }
    }

    #[test]
    fn validates_and_builds_ast() {
        let ont = sample_ontology();
        let validated = validate_intent(&ont, sample_intent()).unwrap();
        let ast = build_ast(&ont, &validated).unwrap();
        assert_eq!(ast.filters.len(), 1);
        assert_eq!(ast.limit, Some(10));
    }

    #[test]
    fn rejects_unknown_class() {
        let ont = sample_ontology();
        let mut intent = sample_intent();
        intent.start.class = "Robot".into();
        assert!(validate_intent(&ont, intent).is_err());
    }
}
