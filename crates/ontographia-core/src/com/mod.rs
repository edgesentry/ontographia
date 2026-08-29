use indexmap::IndexMap;
use serde::{Deserialize, Serialize};

/// Canonical Ontology Model — internal IR shared by all adapters and the query pipeline.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CanonicalOntology {
    pub classes: Vec<ClassDef>,
    pub relationships: Vec<RelDef>,
    pub properties: Vec<PropertyDef>,
    #[serde(default)]
    pub constraints: Vec<Constraint>,
    #[serde(default)]
    pub namespaces: NamespaceMap,
    #[serde(default)]
    pub source: SourceMetadata,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ClassDef {
    pub name: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub iri: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub super_classes: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RelDef {
    pub name: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub iri: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub from_class: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub to_class: Option<String>,
    #[serde(default)]
    pub direction: RelDirection,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "lowercase")]
pub enum RelDirection {
    #[default]
    Out,
    In,
    Both,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PropertyDef {
    pub name: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub iri: Option<String>,
    pub owner_class: String,
    pub datatype: Datatype,
    #[serde(default)]
    pub required: bool,
    #[serde(default)]
    pub unique: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Datatype {
    String,
    Integer,
    Float,
    Boolean,
    Date,
    DateTime,
    Iri,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Constraint {
    pub kind: ConstraintKind,
    pub target_class: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub property: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub value: Option<serde_json::Value>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ConstraintKind {
    MinCount,
    MaxCount,
    Datatype,
    Pattern,
    In,
}

pub type NamespaceMap = IndexMap<String, String>;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct SourceMetadata {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub format: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub uri: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub version: Option<String>,
}

impl CanonicalOntology {
    pub fn class_names(&self) -> Vec<&str> {
        self.classes.iter().map(|c| c.name.as_str()).collect()
    }

    pub fn relationship_names(&self) -> Vec<&str> {
        self.relationships.iter().map(|r| r.name.as_str()).collect()
    }

    pub fn properties_for_class(&self, class_name: &str) -> Vec<&PropertyDef> {
        let ancestors = self.ancestor_classes(class_name);
        self.properties
            .iter()
            .filter(|p| ancestors.iter().any(|c| c == &p.owner_class))
            .collect()
    }

    pub fn expand_class(&self, class_name: &str) -> Vec<String> {
        let mut result = vec![class_name.to_string()];
        let mut queue = vec![class_name.to_string()];
        while let Some(current) = queue.pop() {
            for class in &self.classes {
                if class.super_classes.contains(&current) && !result.contains(&class.name) {
                    result.push(class.name.clone());
                    queue.push(class.name.clone());
                }
            }
        }
        result
    }

    pub fn ancestor_classes(&self, class_name: &str) -> Vec<String> {
        let mut result = vec![class_name.to_string()];
        let mut queue = vec![class_name.to_string()];
        while let Some(current) = queue.pop() {
            if let Some(class) = self.classes.iter().find(|c| c.name == current) {
                for parent in &class.super_classes {
                    if !result.contains(parent) {
                        result.push(parent.clone());
                        queue.push(parent.clone());
                    }
                }
            }
        }
        result
    }

    pub fn resolve_class(&self, name: &str) -> Option<&ClassDef> {
        self.classes.iter().find(|c| c.name == name)
    }

    pub fn resolve_relationship(&self, name: &str) -> Option<&RelDef> {
        self.relationships.iter().find(|r| r.name == name)
    }

    pub fn resolve_property(&self, class_name: &str, property_name: &str) -> Option<&PropertyDef> {
        let ancestors = self.ancestor_classes(class_name);
        self.properties.iter().find(|p| {
            p.name == property_name && ancestors.iter().any(|c| c == &p.owner_class)
        })
    }

    pub fn is_subclass_of(&self, child: &str, parent: &str) -> bool {
        if child == parent {
            return true;
        }
        self.expand_class(parent).iter().any(|c| c == child)
            || self
                .classes
                .iter()
                .find(|c| c.name == child)
                .map(|c| c.super_classes.iter().any(|s| self.is_subclass_of(s, parent)))
                .unwrap_or(false)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample() -> CanonicalOntology {
        CanonicalOntology {
            classes: vec![
                ClassDef {
                    name: "Person".into(),
                    iri: None,
                    super_classes: vec![],
                    description: None,
                },
                ClassDef {
                    name: "Employee".into(),
                    iri: None,
                    super_classes: vec!["Person".into()],
                    description: None,
                },
            ],
            relationships: vec![RelDef {
                name: "knows".into(),
                iri: None,
                from_class: Some("Person".into()),
                to_class: Some("Person".into()),
                direction: RelDirection::Out,
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
            namespaces: IndexMap::new(),
            source: SourceMetadata::default(),
        }
    }

    #[test]
    fn expand_class_includes_subclasses() {
        let ont = sample();
        let expanded = ont.expand_class("Person");
        assert!(expanded.contains(&"Person".to_string()));
        assert!(expanded.contains(&"Employee".to_string()));
    }

    #[test]
    fn resolve_property_via_inheritance() {
        let ont = sample();
        assert!(ont.resolve_property("Employee", "age").is_some());
    }
}
