use crate::ast::EmittedQuery;
use crate::builder::{build_ast, validate_intent};
use crate::com::CanonicalOntology;
use crate::emit::{emit_query, Dialect};
use crate::error::Result;
use crate::intent::Intent;
use crate::schema_gen::intent_json_schema;

#[derive(Debug, Clone)]
pub struct Engine {
    ontology: CanonicalOntology,
}

impl Engine {
    pub fn new(ontology: CanonicalOntology) -> Self {
        Self { ontology }
    }

    pub fn ontology(&self) -> &CanonicalOntology {
        &self.ontology
    }

    pub fn intent_json_schema(&self) -> serde_json::Value {
        intent_json_schema(&self.ontology)
    }

    pub fn build(&self, intent: Intent, dialect: Dialect) -> Result<EmittedQuery> {
        let validated = validate_intent(&self.ontology, intent)?;
        let ast = build_ast(&self.ontology, &validated)?;
        emit_query(dialect, &ast, &validated.params)
    }

    pub fn build_from_json(
        &self,
        intent_json: &serde_json::Value,
        dialect: Dialect,
    ) -> Result<EmittedQuery> {
        let intent: Intent = serde_json::from_value(intent_json.clone())?;
        self.build(intent, dialect)
    }
}
