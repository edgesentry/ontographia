use indexmap::IndexMap;
use ontographia_core::com::Datatype;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct GraphSchema {
    pub labels: IndexMap<String, LabelSchema>,
    pub relationship_types: IndexMap<String, RelSchema>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct LabelSchema {
    pub properties: IndexMap<String, Datatype>,
    pub unique_properties: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RelSchema {
    pub from_class: Option<String>,
    pub to_class: Option<String>,
}

/// Offline snapshot of a Neo4j catalog (labels / relationship types).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct GraphSnapshot {
    pub labels: Vec<String>,
    pub relationship_types: Vec<String>,
    #[serde(default)]
    pub node_properties: IndexMap<String, Vec<String>>,
}

impl GraphSnapshot {
    pub fn from_json(value: &serde_json::Value) -> crate::error::Result<Self> {
        Ok(serde_json::from_value(value.clone())?)
    }

    pub fn from_json_str(text: &str) -> crate::error::Result<Self> {
        Ok(serde_json::from_str(text)?)
    }
}
