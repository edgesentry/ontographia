use indexmap::IndexMap;
use ontographia_core::com::CanonicalOntology;

use crate::model::{GraphSchema, LabelSchema, RelSchema};

impl GraphSchema {
    pub fn from_com(ontology: &CanonicalOntology) -> Self {
        let mut labels = IndexMap::new();

        for class in &ontology.classes {
            labels.insert(
                class.name.clone(),
                LabelSchema {
                    properties: IndexMap::new(),
                    unique_properties: Vec::new(),
                },
            );
        }

        for prop in &ontology.properties {
            if let Some(label) = labels.get_mut(&prop.owner_class) {
                label.properties.insert(prop.name.clone(), prop.datatype.clone());
                if prop.unique {
                    label.unique_properties.push(prop.name.clone());
                }
            }
        }

        for label in labels.values_mut() {
            label.unique_properties.sort();
            label.unique_properties.dedup();
        }

        let relationship_types = ontology
            .relationships
            .iter()
            .map(|rel| {
                (
                    rel.name.clone(),
                    RelSchema {
                        from_class: rel.from_class.clone(),
                        to_class: rel.to_class.clone(),
                    },
                )
            })
            .collect();

        Self {
            labels,
            relationship_types,
        }
    }
}
