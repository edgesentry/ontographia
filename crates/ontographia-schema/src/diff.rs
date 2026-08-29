use crate::model::{GraphSchema, GraphSnapshot};

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct SchemaDiff {
    pub missing_labels: Vec<String>,
    pub extra_labels: Vec<String>,
    pub missing_relationship_types: Vec<String>,
    pub extra_relationship_types: Vec<String>,
}

pub fn diff(expected: &GraphSchema, actual: &GraphSnapshot) -> SchemaDiff {
    let expected_labels: Vec<String> = expected.labels.keys().cloned().collect();
    let expected_rels: Vec<String> = expected.relationship_types.keys().cloned().collect();

    SchemaDiff {
        missing_labels: diff_missing(&expected_labels, &actual.labels),
        extra_labels: diff_extra(&expected_labels, &actual.labels),
        missing_relationship_types: diff_missing(&expected_rels, &actual.relationship_types),
        extra_relationship_types: diff_extra(&expected_rels, &actual.relationship_types),
    }
}

pub fn diff_has_errors(diff: &SchemaDiff) -> bool {
    !diff.missing_labels.is_empty()
        || !diff.extra_labels.is_empty()
        || !diff.missing_relationship_types.is_empty()
        || !diff.extra_relationship_types.is_empty()
}

fn diff_missing(expected: &[String], actual: &[String]) -> Vec<String> {
    let mut missing = Vec::new();
    for item in expected {
        if !actual.iter().any(|a| a == item) {
            missing.push(item.clone());
        }
    }
    missing.sort();
    missing
}

fn diff_extra(expected: &[String], actual: &[String]) -> Vec<String> {
    let mut extra = Vec::new();
    for item in actual {
        if !expected.iter().any(|e| e == item) {
            extra.push(item.clone());
        }
    }
    extra.sort();
    extra
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::{GraphSchema, LabelSchema};
    use indexmap::IndexMap;

    #[test]
    fn detects_missing_label() {
        let expected = GraphSchema {
            labels: IndexMap::from([(
                "Product".into(),
                LabelSchema {
                    properties: IndexMap::new(),
                    unique_properties: vec![],
                },
            )]),
            relationship_types: IndexMap::new(),
        };
        let actual = GraphSnapshot {
            labels: vec![],
            relationship_types: vec![],
            node_properties: IndexMap::new(),
        };

        let result = diff(&expected, &actual);
        assert!(diff_has_errors(&result));
        assert_eq!(result.missing_labels, vec!["Product"]);
    }
}
