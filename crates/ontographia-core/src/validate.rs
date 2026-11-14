use crate::ast::{
    FilterNode, MatchClause, NodePattern, PatternNode, QueryAst, RelPattern, ReturnExpr,
    ReturnNode, SubPatternNode,
};
use crate::com::CanonicalOntology;
use crate::error::{OntographiaError, Result};
use crate::intent::{Intent, ReturnItem, TraverseStep};
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

    // Sub-pattern parameter numbers continue after the main filters, in
    // Intent order. A correlated alias is bound in the main pattern, so its
    // node pattern is emitted without a label.
    let mut param_index = intent.filter.len();
    let not_exists: Vec<SubPatternNode> = intent
        .not_exists
        .iter()
        .map(|sub| {
            let node_for = |node: &crate::intent::NodeRef| NodePattern {
                alias: node.alias.clone(),
                labels: if intent.start.alias.as_str() == node.alias
                    || intent.traverse.iter().any(|s| s.to.alias == node.alias)
                {
                    vec![]
                } else {
                    vec![node.class.clone()]
                },
            };

            let mut nodes = vec![node_for(&sub.start)];
            let mut relationships = Vec::new();
            for step in &sub.traverse {
                relationships.push(RelPattern {
                    alias: None,
                    rel_type: step.relationship.clone(),
                    direction: step.direction,
                    min_hops: step.min_hops,
                    max_hops: step.max_hops,
                });
                nodes.push(node_for(&step.to));
            }

            let filters: Vec<FilterNode> = sub
                .filter
                .iter()
                .map(|f| {
                    let node = FilterNode {
                        alias: f.alias.clone(),
                        property: f.property.clone(),
                        op: f.op,
                        param_name: format!("param_{}", param_index),
                    };
                    param_index += 1;
                    node
                })
                .collect();

            SubPatternNode {
                pattern: PatternNode {
                    nodes,
                    relationships,
                },
                filters,
            }
        })
        .collect();

    let returns: Vec<ReturnNode> = intent.r#return.iter().map(map_return_item).collect();

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
        not_exists,
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

/// Validate one relationship hop: the relationship exists, it originates from
/// `prev_class`, the target class exists, and it accepts the target class.
///
/// Shared by the main pattern and `not_exists` sub-patterns so both keep the
/// same `direction` behaviour (including the current inbound rule).
fn validate_traverse_step(
    ontology: &CanonicalOntology,
    step: &TraverseStep,
    prev_class: &str,
) -> Result<()> {
    let rel = ontology
        .resolve_relationship(&step.relationship)
        .ok_or_else(|| {
            OntographiaError::Validation(format!("unknown relationship: {}", step.relationship))
        })?;

    if let Some(from) = &rel.from_class {
        if !ontology.is_subclass_of(prev_class, from) && prev_class != *from {
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
    Ok(())
}

pub fn validate_intent(ontology: &CanonicalOntology, intent: Intent) -> Result<ValidatedIntent> {
    if intent.optional && !intent.not_exists.is_empty() {
        return Err(OntographiaError::Validation(
            "optional: true cannot be combined with not_exists".into(),
        ));
    }

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

        validate_traverse_step(ontology, step, &prev_class)?;
        prev_class = step.to.class.clone();
    }

    // Aliases offered by not_exists sub-patterns. Used only to explain why a
    // sub-pattern-only alias cannot be used in the main filter / return /
    // order_by; correlated aliases are already part of `aliases`.
    let sub_aliases: Vec<String> = intent
        .not_exists
        .iter()
        .flat_map(|sub| {
            std::iter::once(sub.start.alias.clone())
                .chain(sub.traverse.iter().map(|step| step.to.alias.clone()))
        })
        .collect();

    for f in &intent.filter {
        require_safe_ident("filter.alias", &f.alias)?;
        require_safe_ident("filter.property", &f.property)?;
        if !aliases.contains(&f.alias) {
            if sub_aliases.contains(&f.alias) {
                return Err(OntographiaError::Validation(format!(
                    "filter alias '{}' is only bound inside not_exists",
                    f.alias
                )));
            }
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

    // New aliases introduced by sub-patterns, across the whole Intent.
    let mut new_sub_aliases: Vec<String> = Vec::new();

    for (i, sub) in intent.not_exists.iter().enumerate() {
        if sub.traverse.is_empty() {
            return Err(OntographiaError::Validation(format!(
                "not_exists[{i}]: sub-pattern must have at least one traverse step"
            )));
        }

        let mut local_aliases: Vec<String> = Vec::new();
        let mut class_by_alias: Vec<(String, String)> = Vec::new();
        let mut entry_correlated = 0usize;

        let mut bind = |node: &crate::intent::NodeRef| -> Result<()> {
            if local_aliases.contains(&node.alias) {
                return Err(OntographiaError::Validation(format!(
                    "not_exists[{i}]: duplicate alias: {}",
                    node.alias
                )));
            }
            if aliases.contains(&node.alias) {
                // Correlation: the sub-pattern reuses a main-pattern alias and
                // must declare the same class.
                entry_correlated += 1;
                let main_class = find_class_for_alias(&intent, &node.alias)?;
                if main_class != node.class {
                    return Err(OntographiaError::Validation(format!(
                        "not_exists[{i}]: correlated alias '{}' is bound to class '{}' in the \
                         main pattern but declared as '{}'",
                        node.alias, main_class, node.class
                    )));
                }
            } else {
                if new_sub_aliases.contains(&node.alias) {
                    return Err(OntographiaError::Validation(format!(
                        "not_exists[{i}]: duplicate alias: {}",
                        node.alias
                    )));
                }
                new_sub_aliases.push(node.alias.clone());
            }
            local_aliases.push(node.alias.clone());
            class_by_alias.push((node.alias.clone(), node.class.clone()));
            Ok(())
        };

        require_safe_ident(&format!("not_exists[{i}].start.alias"), &sub.start.alias)?;
        if ontology.resolve_class(&sub.start.class).is_none() {
            return Err(OntographiaError::Validation(format!(
                "unknown class: {}",
                sub.start.class
            )));
        }
        bind(&sub.start)?;

        let mut sub_prev_class = sub.start.class.clone();
        for step in &sub.traverse {
            require_safe_ident(
                &format!("not_exists[{i}].traverse.to.alias"),
                &step.to.alias,
            )?;
            if ontology.resolve_class(&step.to.class).is_none() {
                return Err(OntographiaError::Validation(format!(
                    "unknown class: {}",
                    step.to.class
                )));
            }
            bind(&step.to)?;
            validate_traverse_step(ontology, step, &sub_prev_class)?;
            sub_prev_class = step.to.class.clone();
        }

        if entry_correlated == 0 {
            return Err(OntographiaError::Validation(format!(
                "not_exists[{i}]: no correlated alias (a sub-pattern must reuse at least one \
                 alias bound in the main pattern)"
            )));
        }

        for f in &sub.filter {
            require_safe_ident(&format!("not_exists[{i}].filter.alias"), &f.alias)?;
            require_safe_ident(&format!("not_exists[{i}].filter.property"), &f.property)?;
            let class = class_by_alias
                .iter()
                .find(|(alias, _)| alias == &f.alias)
                .map(|(_, class)| class.clone())
                .ok_or_else(|| {
                    OntographiaError::Validation(format!(
                        "not_exists[{i}]: filter alias not in sub-pattern: {}",
                        f.alias
                    ))
                })?;
            ontology
                .resolve_property(&class, &f.property)
                .ok_or_else(|| {
                    OntographiaError::Validation(format!(
                        "unknown property '{}' on class '{}'",
                        f.property, class
                    ))
                })?;
        }
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
            if sub_aliases.contains(&r.alias) {
                return Err(OntographiaError::Validation(format!(
                    "return alias '{}' is only bound inside not_exists",
                    r.alias
                )));
            }
            return Err(OntographiaError::Validation(format!(
                "return alias not in pattern: {}",
                r.alias
            )));
        }
        if let Some(prop) = &r.property {
            let class = find_class_for_alias(&intent, &r.alias)?;
            ontology.resolve_property(&class, prop).ok_or_else(|| {
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
                ontology.resolve_property(&class, prop).ok_or_else(|| {
                    OntographiaError::Validation(format!(
                        "unknown property '{}' on class '{}' in order_by",
                        prop, class
                    ))
                })?;
            }
        } else if sub_aliases.contains(&order.alias) {
            return Err(OntographiaError::Validation(format!(
                "order_by alias '{}' is only bound inside not_exists",
                order.alias
            )));
        } else {
            return Err(OntographiaError::Validation(format!(
                "order_by alias '{}' is not a pattern alias or projected as_name",
                order.alias
            )));
        }
        // Direction is a boolean on Intent (`descending` → ASC/DESC only); no
        // free-form direction string is accepted by the schema.
    }

    // Main filters first (`param_0..param_{n-1}`), then every sub-pattern's
    // filters in Intent order, continuing the same counter.
    let mut params = IndexMap::new();
    let mut param_index = 0usize;
    for f in &intent.filter {
        params.insert(format!("param_{param_index}"), f.value.clone());
        param_index += 1;
    }
    for sub in &intent.not_exists {
        for f in &sub.filter {
            params.insert(format!("param_{param_index}"), f.value.clone());
            param_index += 1;
        }
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
    use crate::intent::{
        Direction, FilterExpr, FilterOp, NodeRef, OrderBy, ReturnItem, SubPattern, TraverseStep,
    };

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
            not_exists: vec![],
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

    fn part_usage_ontology() -> CanonicalOntology {
        CanonicalOntology {
            classes: vec![
                ClassDef {
                    name: "Part".into(),
                    iri: None,
                    super_classes: vec![],
                    description: None,
                },
                ClassDef {
                    name: "Usage".into(),
                    iri: None,
                    super_classes: vec![],
                    description: None,
                },
            ],
            relationships: vec![
                RelDef {
                    name: "USES_ITEM".into(),
                    iri: None,
                    from_class: Some("Usage".into()),
                    to_class: Some("Part".into()),
                    direction: crate::com::RelDirection::Out,
                },
                // Reverse hop used only to test a correlated alias at the
                // start of a sub-pattern without relying on inbound traversal.
                RelDef {
                    name: "HAS_USAGE".into(),
                    iri: None,
                    from_class: Some("Part".into()),
                    to_class: Some("Usage".into()),
                    direction: crate::com::RelDirection::Out,
                },
            ],
            properties: vec![
                PropertyDef {
                    name: "name".into(),
                    iri: None,
                    owner_class: "Part".into(),
                    datatype: Datatype::String,
                    required: false,
                    unique: false,
                },
                PropertyDef {
                    name: "category_slug".into(),
                    iri: None,
                    owner_class: "Part".into(),
                    datatype: Datatype::String,
                    required: false,
                    unique: false,
                },
                PropertyDef {
                    name: "match_method".into(),
                    iri: None,
                    owner_class: "Usage".into(),
                    datatype: Datatype::String,
                    required: false,
                    unique: false,
                },
            ],
            constraints: vec![],
            namespaces: indexmap::IndexMap::new(),
            source: Default::default(),
        }
    }

    fn node(class: &str, alias: &str) -> NodeRef {
        NodeRef {
            class: class.into(),
            alias: alias.into(),
        }
    }

    fn filter(alias: &str, property: &str, value: serde_json::Value) -> FilterExpr {
        FilterExpr {
            alias: alias.into(),
            property: property.into(),
            op: FilterOp::Eq,
            value,
        }
    }

    fn step(relationship: &str, direction: Direction, to: NodeRef) -> TraverseStep {
        TraverseStep {
            relationship: relationship.into(),
            direction,
            to,
            min_hops: None,
            max_hops: None,
        }
    }

    fn usage_not_exists(start: NodeRef, to: NodeRef) -> SubPattern {
        SubPattern {
            start,
            traverse: vec![step("USES_ITEM", Direction::Out, to)],
            filter: vec![filter("u", "match_method", serde_json::json!("exact"))],
        }
    }

    /// The Intent from the issue text.
    fn not_exists_intent() -> Intent {
        Intent {
            start: node("Part", "part"),
            traverse: vec![],
            filter: vec![filter(
                "part",
                "category_slug",
                serde_json::json!("fasteners-and-hardware"),
            )],
            not_exists: vec![usage_not_exists(node("Usage", "u"), node("Part", "part"))],
            r#return: vec![ReturnItem {
                alias: "part".into(),
                property: Some("name".into()),
                aggregate: None,
                as_name: Some("part".into()),
            }],
            order_by: None,
            limit: Some(200),
            skip: None,
            optional: false,
        }
    }

    fn emit(intent: Intent, dialect: crate::emit::Dialect) -> crate::ast::EmittedQuery {
        let ontology = part_usage_ontology();
        let validated = validate_intent(&ontology, intent).expect("validate");
        let ast = build_ast(&ontology, &validated).unwrap();
        crate::emit::emit_query(dialect, &ast, &validated.params).unwrap()
    }

    #[test]
    fn not_exists_emits_exact_cypher25() {
        let emitted = emit(not_exists_intent(), crate::emit::Dialect::Cypher25);
        assert_eq!(
            emitted.query,
            "CYPHER 25\n\
             MATCH (part:Part)\n\
             FILTER part.category_slug = $param_0 AND NOT EXISTS { MATCH (u:Usage)-[:USES_ITEM]->(part) FILTER u.match_method = $param_1 }\n\
             RETURN part.name AS part\n\
             LIMIT 200"
        );
        assert_eq!(
            emitted.params.get("param_0"),
            Some(&serde_json::json!("fasteners-and-hardware"))
        );
        assert_eq!(
            emitted.params.get("param_1"),
            Some(&serde_json::json!("exact"))
        );
    }

    #[test]
    fn not_exists_emits_cypher5_with_inner_where() {
        let emitted = emit(not_exists_intent(), crate::emit::Dialect::Cypher5);
        assert_eq!(
            emitted.query,
            "CYPHER 5\n\
             MATCH (part:Part)\n\
             WHERE part.category_slug = $param_0 AND NOT EXISTS { MATCH (u:Usage)-[:USES_ITEM]->(part) WHERE u.match_method = $param_1 }\n\
             RETURN part.name AS part\n\
             LIMIT 200"
        );
        assert!(!emitted.query.contains("FILTER"), "{}", emitted.query);
    }

    #[test]
    fn not_exists_without_main_filters_emits_filter_not_exists() {
        let mut intent = not_exists_intent();
        intent.filter.clear();
        let emitted = emit(intent, crate::emit::Dialect::Cypher25);
        assert!(
            emitted.query.contains(
                "FILTER NOT EXISTS { MATCH (u:Usage)-[:USES_ITEM]->(part) FILTER u.match_method = $param_0 }"
            ),
            "{}",
            emitted.query
        );
        // Sub-pattern numbering starts at param_0 when there are no main filters.
        assert_eq!(
            emitted.params.keys().cloned().collect::<Vec<_>>(),
            vec!["param_0".to_string()]
        );
    }

    #[test]
    fn not_exists_sub_pattern_without_filter_omits_inner_filter() {
        let mut intent = not_exists_intent();
        intent.not_exists[0].filter.clear();
        let emitted = emit(intent, crate::emit::Dialect::Cypher25);
        assert!(
            emitted.query.contains(
                "FILTER part.category_slug = $param_0 AND NOT EXISTS { MATCH (u:Usage)-[:USES_ITEM]->(part) }"
            ),
            "{}",
            emitted.query
        );
        assert!(!emitted.query.contains("$param_1"), "{}", emitted.query);
    }

    #[test]
    fn not_exists_two_entries_number_params_in_intent_order() {
        let mut intent = not_exists_intent();
        intent.not_exists.push(SubPattern {
            start: node("Usage", "u2"),
            traverse: vec![step("USES_ITEM", Direction::Out, node("Part", "part"))],
            filter: vec![filter("u2", "match_method", serde_json::json!("fuzzy"))],
        });
        let emitted = emit(intent.clone(), crate::emit::Dialect::Cypher25);
        assert!(
            emitted.query.contains(
                "NOT EXISTS { MATCH (u:Usage)-[:USES_ITEM]->(part) FILTER u.match_method = $param_1 } AND NOT EXISTS { MATCH (u2:Usage)-[:USES_ITEM]->(part) FILTER u2.match_method = $param_2 }"
            ),
            "{}",
            emitted.query
        );
        assert_eq!(
            emitted.params.keys().cloned().collect::<Vec<_>>(),
            vec![
                "param_0".to_string(),
                "param_1".to_string(),
                "param_2".to_string()
            ]
        );
        assert_eq!(
            emitted.params.get("param_2"),
            Some(&serde_json::json!("fuzzy"))
        );

        let validated = validate_intent(&part_usage_ontology(), intent).unwrap();
        assert_eq!(
            validated.params.keys().cloned().collect::<Vec<_>>(),
            vec![
                "param_0".to_string(),
                "param_1".to_string(),
                "param_2".to_string()
            ]
        );
    }

    #[test]
    fn not_exists_correlated_alias_at_sub_pattern_start() {
        let mut intent = not_exists_intent();
        intent.not_exists[0] = SubPattern {
            start: node("Part", "part"),
            traverse: vec![step("HAS_USAGE", Direction::Out, node("Usage", "u"))],
            filter: vec![filter("u", "match_method", serde_json::json!("exact"))],
        };
        let validated = validate_intent(&part_usage_ontology(), intent).unwrap();
        let ast = build_ast(&part_usage_ontology(), &validated).unwrap();
        // Correlated node is emitted bare, new node keeps its label.
        assert_eq!(
            ast.not_exists[0].pattern.nodes[0].labels,
            Vec::<String>::new()
        );
        assert_eq!(ast.not_exists[0].pattern.nodes[1].labels, vec!["Usage"]);
        let emitted =
            crate::emit::emit_query(crate::emit::Dialect::Cypher25, &ast, &validated.params)
                .unwrap();
        assert!(
            emitted
                .query
                .contains("NOT EXISTS { MATCH (part)-[:HAS_USAGE]->(u:Usage)"),
            "{}",
            emitted.query
        );
    }

    #[test]
    fn not_exists_requires_a_correlated_alias() {
        let mut intent = not_exists_intent();
        intent.not_exists[0] = usage_not_exists(node("Usage", "u"), node("Part", "p2"));
        let err = validate_intent(&part_usage_ontology(), intent).unwrap_err();
        assert!(
            err.to_string()
                .contains("not_exists[0]: no correlated alias"),
            "{err}"
        );
    }

    #[test]
    fn not_exists_correlated_alias_must_match_main_class() {
        let mut intent = not_exists_intent();
        intent.not_exists[0].traverse[0].to = node("Usage", "part");
        let err = validate_intent(&part_usage_ontology(), intent).unwrap_err();
        let msg = err.to_string();
        assert!(
            msg.contains("correlated alias 'part'")
                && msg.contains("class 'Part'")
                && msg.contains("'Usage'"),
            "{msg}"
        );
    }

    #[test]
    fn not_exists_rejects_duplicate_alias_inside_one_entry() {
        let mut intent = not_exists_intent();
        intent.not_exists[0] = usage_not_exists(node("Usage", "u"), node("Part", "u"));
        let err = validate_intent(&part_usage_ontology(), intent).unwrap_err();
        assert!(
            err.to_string()
                .contains("not_exists[0]: duplicate alias: u"),
            "{err}"
        );
    }

    #[test]
    fn not_exists_rejects_duplicate_alias_across_entries() {
        let mut intent = not_exists_intent();
        intent
            .not_exists
            .push(usage_not_exists(node("Usage", "u"), node("Part", "part")));
        let err = validate_intent(&part_usage_ontology(), intent).unwrap_err();
        assert!(
            err.to_string()
                .contains("not_exists[1]: duplicate alias: u"),
            "{err}"
        );
    }

    #[test]
    fn not_exists_alias_is_rejected_in_return() {
        let mut intent = not_exists_intent();
        intent.r#return = vec![ReturnItem {
            alias: "u".into(),
            property: Some("match_method".into()),
            aggregate: None,
            as_name: None,
        }];
        let err = validate_intent(&part_usage_ontology(), intent).unwrap_err();
        assert!(
            err.to_string()
                .contains("return alias 'u' is only bound inside not_exists"),
            "{err}"
        );
    }

    #[test]
    fn not_exists_alias_is_rejected_in_order_by() {
        let mut intent = not_exists_intent();
        intent.order_by = Some(OrderBy {
            alias: "u".into(),
            property: Some("match_method".into()),
            descending: false,
        });
        let err = validate_intent(&part_usage_ontology(), intent).unwrap_err();
        assert!(
            err.to_string()
                .contains("order_by alias 'u' is only bound inside not_exists"),
            "{err}"
        );
    }

    #[test]
    fn not_exists_alias_is_rejected_in_main_filter() {
        let mut intent = not_exists_intent();
        intent
            .filter
            .push(filter("u", "match_method", serde_json::json!("exact")));
        let err = validate_intent(&part_usage_ontology(), intent).unwrap_err();
        assert!(
            err.to_string()
                .contains("filter alias 'u' is only bound inside not_exists"),
            "{err}"
        );
    }

    #[test]
    fn not_exists_filter_cannot_use_another_entry_alias() {
        let mut intent = not_exists_intent();
        intent.not_exists.push(SubPattern {
            start: node("Usage", "u2"),
            traverse: vec![step("USES_ITEM", Direction::Out, node("Part", "part"))],
            filter: vec![filter("u", "match_method", serde_json::json!("x"))],
        });
        let err = validate_intent(&part_usage_ontology(), intent).unwrap_err();
        assert!(
            err.to_string()
                .contains("not_exists[1]: filter alias not in sub-pattern: u"),
            "{err}"
        );
    }

    #[test]
    fn not_exists_rejects_relationship_origin_mismatch() {
        let mut intent = not_exists_intent();
        intent.not_exists[0] = SubPattern {
            start: node("Part", "part"),
            traverse: vec![step("USES_ITEM", Direction::Out, node("Usage", "u"))],
            filter: vec![],
        };
        let err = validate_intent(&part_usage_ontology(), intent).unwrap_err();
        assert!(
            err.to_string()
                .contains("does not originate from class 'Part'"),
            "{err}"
        );
    }

    #[test]
    fn not_exists_rejects_relationship_target_mismatch() {
        let mut intent = not_exists_intent();
        intent.not_exists[0] = usage_not_exists(node("Usage", "u"), node("Usage", "u2"));
        let err = validate_intent(&part_usage_ontology(), intent).unwrap_err();
        assert!(
            err.to_string().contains("does not target class 'Usage'"),
            "{err}"
        );
    }

    #[test]
    fn not_exists_rejects_unknown_property_in_sub_filter() {
        let mut intent = not_exists_intent();
        intent.not_exists[0].filter[0].property = "nope".into();
        let err = validate_intent(&part_usage_ontology(), intent).unwrap_err();
        assert!(
            err.to_string()
                .contains("unknown property 'nope' on class 'Usage'"),
            "{err}"
        );
    }

    #[test]
    fn not_exists_is_rejected_with_optional() {
        let mut intent = not_exists_intent();
        intent.optional = true;
        let err = validate_intent(&part_usage_ontology(), intent).unwrap_err();
        assert!(
            err.to_string()
                .contains("optional: true cannot be combined with not_exists"),
            "{err}"
        );
    }

    #[test]
    fn not_exists_requires_at_least_one_traverse_step() {
        let mut intent = not_exists_intent();
        intent.not_exists[0].traverse.clear();
        let err = validate_intent(&part_usage_ontology(), intent).unwrap_err();
        assert!(
            err.to_string()
                .contains("not_exists[0]: sub-pattern must have at least one traverse step"),
            "{err}"
        );
    }

    #[test]
    fn ast_without_not_exists_serializes_without_the_field() {
        let ontology = sample_ontology();
        let validated = validate_intent(&ontology, sample_intent()).unwrap();
        let ast = build_ast(&ontology, &validated).unwrap();
        let value = serde_json::to_value(&ast).unwrap();
        assert!(value.get("not_exists").is_none(), "{value}");
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
        assert!(err.to_string().contains("order_by alias"), "{err}");
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
        assert!(err.to_string().contains("not projected in return"), "{err}");
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
        let emitted = Cypher25Emitter.emit(&ast, &validated.params).unwrap();
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
