use ontographia_core::com::CanonicalOntology;
use ontographia_core::error::{OntographiaError, Result};

pub trait OntologyAdapter {
    fn name(&self) -> &'static str;
    fn detect(source: &[u8], path_hint: Option<&str>) -> bool;
    fn parse(source: &[u8]) -> Result<CanonicalOntology>
    where
        Self: Sized;
    fn supported_extensions() -> &'static [&'static str];
}

pub struct AdapterRegistry;

impl AdapterRegistry {
    pub fn load(source: &[u8], path_hint: Option<&str>) -> Result<CanonicalOntology> {
        if crate::native_yaml::NativeYamlAdapter::detect(source, path_hint) {
            return crate::native_yaml::NativeYamlAdapter::parse(source);
        }
        if crate::linkml::LinkMlAdapter::detect(source, path_hint) {
            return crate::linkml::LinkMlAdapter::parse(source);
        }
        if crate::obo::OboAdapter::detect(source, path_hint) {
            return crate::obo::OboAdapter::parse(source);
        }
        if crate::jsonld::JsonLdAdapter::detect(source, path_hint) {
            return crate::jsonld::JsonLdAdapter::parse(source);
        }
        if crate::turtle_owl::TurtleOwlAdapter::detect(source, path_hint) {
            return crate::turtle_owl::TurtleOwlAdapter::parse(source);
        }
        if crate::shacl::ShaclAdapter::detect(source, path_hint) {
            return crate::shacl::ShaclAdapter::parse(source);
        }
        if crate::skos::SkosAdapter::detect(source, path_hint) {
            return crate::skos::SkosAdapter::parse(source);
        }

        Err(OntographiaError::UnsupportedFormat(
            "could not detect ontology format".into(),
        ))
    }
}

pub fn load_ontology(source: &[u8], path_hint: Option<&str>) -> Result<CanonicalOntology> {
    AdapterRegistry::load(source, path_hint)
}

pub fn load_ontology_from_path(path: impl AsRef<std::path::Path>) -> Result<CanonicalOntology> {
    let path = path.as_ref();
    let bytes = std::fs::read(path)?;
    AdapterRegistry::load(&bytes, path.to_str())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn loads_native_yaml_by_extension() {
        let yaml = include_str!("../../../examples/manufacturing.native.yaml");
        let ont = load_ontology(yaml.as_bytes(), Some("manufacturing.native.yaml")).unwrap();
        assert!(!ont.classes.is_empty());
    }
}
