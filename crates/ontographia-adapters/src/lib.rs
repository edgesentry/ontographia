pub mod jsonld;
pub mod linkml;
pub mod native_yaml;
pub mod obo;
pub mod registry;
pub mod shacl;
pub mod skos;
pub mod turtle_owl;

pub use registry::{load_ontology, load_ontology_from_path, AdapterRegistry};
