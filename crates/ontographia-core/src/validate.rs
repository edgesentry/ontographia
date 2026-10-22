use crate::ast::{
    FilterNode, MatchClause, NodePattern, PatternNode, QueryAst, RelPattern, ReturnExpr, ReturnNode,
};
use crate::com::CanonicalOntology;
use crate::error::{OntographiaError, Result};
use crate::intent::{Intent, ReturnItem};
use indexmap::IndexMap;

/// Cypher unquoted identifiers interpolated from Intent (`alias`, `as_name`, …).
/// Reject anything outside this grammar so hostile fragments cannot break out of
/// identifier positions in emitted Cypher.
pub fn is_safe_cypher_ident(name: &str) -> bool {
    let mut chars = name.chars();
    match chars.next() {
        Some(c) if c.is_ascii_alphabetic() || c == '_' => {}
        _ => return false,
    }
    chars.all(|c| c.is_ascii_alphanumeric() || c == '_')
}

fn require_safe_ident(field: &str, name: &str) -> Result<()> {
    if is_safe_cypher_ident(name) {
        Ok(())
    } else {
        Err(OntographiaError::Validation(format!(
            "invalid Cypher identifier in {field}: {name:?} \
             (must match ^[A-Za-z_][A-Za-z0-9_]*$)"
        )))
    }
}

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

    require_safe_ident("start.alias", &intent.start.alias)?;

    let mut aliases = vec![intent.start.alias.clone()];
    let mut prev_class = intent.start.class.clone();

    for step in &intent.traverse {
        require_safe_ident("traverse.to.alias", &step.to.alias)?;
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
        require_safe_ident("filter.alias", &f.alias)?;
        require_safe_ident("filter.property", &f.property)?;
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

    let mut projected_as_names = Vec::new();
    for r in &intent.r#return {
        require_safe_ident("return.alias", &r.alias)?;
        if let Some(prop) = &r.property {
            require_safe_ident("return.property", prop)?;
        }
        if let Some(as_name) = &r.as_name {
            require_safe_ident("return.as_name", as_name)?;
            projected_as_names.push(as_name.clone());
        }
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

    if let Some(order) = &intent.order_by {
        require_safe_ident("order_by.alias", &order.alias)?;
        if let Some(prop) = &order.property {
            require_safe_ident("order_by.property", prop)?;
        }

        let order_by_as_name = projected_as_names.iter().any(|a| a == &order.alias);
        let order_by_pattern = aliases.contains(&order.alias);

        if order_by_as_name {
            // ORDER BY projected AS name — no property path.
            if order.property.is_some() {
                return Err(OntographiaError::Validation(format!(
                    "order_by.property must be omitted when ordering by projected as_name '{}'",
                    order.alias
                )));
            }
        } else if order_by_pattern {
            // Must reference a returned pattern alias (projected).
            let in_return = intent.r#return.iter().any(|r| r.alias == order.alias);
            if !in_return {
                return Err(OntographiaError::Validation(format!(
                    "order_by alias '{}' is not projected in return",
                    order.alias
                )));
            }
            if let Some(prop) = &order.property {
                let class = find_class_for_alias(&intent, &order.alias)?;
                ontology
                    .resolve_property(&class, prop)
                    .ok_or_else(|| {
                        OntographiaError::Validation(format!(
                            "unknown property '{}' on class '{}' in order_by",
                            prop, class
                        ))
                    })?;
            }
        } else {
            return Err(OntographiaError::Validation(format!(
                "order_by alias '{}' is not a pattern alias or projected as_name",
                order.alias
            )));
        }
        // Direction is a boolean on Intent (`descending` → ASC/DESC only); no
        // free-form direction string is accepted by the schema.
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
    use crate::emit::{Cypher25Emitter, QueryEmitter};
    use crate::intent::{FilterExpr, FilterOp, NodeRef, OrderBy, ReturnItem, TraverseStep};
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
                    unique: false,
                },
                PropertyDef {
                    name: "age".into(),
                    iri: None,
                    owner_class: "Person".into(),
                    datatype: Datatype::Integer,
                    required: false,
                    unique: false,
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

    /// Before identifier validation, hostile `as_name` values were interpolated
    /// into Cypher and could break out of the AS clause (backticks, comments,
    /// extra RETURN fragments). This test locks the rejection.
    #[test]
    fn rejects_hostile_as_name_breakout() {
        let ont = sample_ontology();
        let hostile = [
            "name` RETURN 1 //",
            "name} RETURN 1 //",
            "name RETURN 1",
            "x AS y",
            "n; MATCH (x)",
        ];
        for as_name in hostile {
            let mut intent = sample_intent();
            intent.r#return[0].as_name = Some(as_name.into());
            let err = validate_intent(&ont, intent).expect_err(as_name);
            let msg = err.to_string();
            assert!(
                msg.contains("invalid Cypher identifier") && msg.contains("as_name"),
                "as_name={as_name:?}: {msg}"
            );
        }
    }

    #[test]
    fn rejects_hostile_alias_breakout() {
        let ont = sample_ontology();
        let mut intent = sample_intent();
        // Keep filter/return aliases consistent so only start.alias triggers.
        intent.start.alias = "p} //".into();
        intent.filter[0].alias = "p} //".into();
        let err = validate_intent(&ont, intent).expect_err("hostile start.alias");
        assert!(
            err.to_string().contains("invalid Cypher identifier"),
            "{err}"
        );
    }

    #[test]
    fn rejects_order_by_unknown_alias() {
        let ont = sample_ontology();
        let mut intent = sample_intent();
        intent.order_by = Some(OrderBy {
            alias: "missing".into(),
            property: Some("name".into()),
            descending: false,
        });
        let err = validate_intent(&ont, intent).expect_err("unknown order_by");
        assert!(
            err.to_string().contains("order_by alias"),
            "{err}"
        );
    }

    #[test]
    fn rejects_order_by_alias_not_in_return() {
        let ont = sample_ontology();
        let mut intent = sample_intent();
        // `p` is in the pattern and used by filter, but not projected in return.
        intent.order_by = Some(OrderBy {
            alias: "p".into(),
            property: Some("age".into()),
            descending: true,
        });
        let err = validate_intent(&ont, intent).expect_err("unprojected order_by");
        assert!(
            err.to_string().contains("not projected in return"),
            "{err}"
        );
    }

    #[test]
    fn accepts_order_by_projected_property_and_as_name() {
        let ont = sample_ontology();
        let mut intent = sample_intent();
        intent.order_by = Some(OrderBy {
            alias: "friend".into(),
            property: Some("name".into()),
            descending: true,
        });
        validate_intent(&ont, intent.clone()).expect("pattern+property order_by");

        intent.order_by = Some(OrderBy {
            alias: "name".into(),
            property: None,
            descending: false,
        });
        let validated = validate_intent(&ont, intent).expect("as_name order_by");
        let ast = build_ast(&ont, &validated).unwrap();
        let emitted = Cypher25Emitter
            .emit(&ast, &validated.params)
            .unwrap();
        assert!(emitted.query.contains("ORDER BY name ASC"));
    }

    #[test]
    fn accepts_safe_identifiers() {
        assert!(is_safe_cypher_ident("p"));
        assert!(is_safe_cypher_ident("_x"));
        assert!(is_safe_cypher_ident("supplier_name"));
        assert!(!is_safe_cypher_ident(""));
        assert!(!is_safe_cypher_ident("1a"));
        assert!(!is_safe_cypher_ident("a-b"));
        assert!(!is_safe_cypher_ident("a b"));
        assert!(!is_safe_cypher_ident("a`b"));
    }
}
