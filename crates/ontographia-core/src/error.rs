use thiserror::Error;

pub type Result<T> = std::result::Result<T, OntographiaError>;

#[derive(Debug, Error)]
pub enum OntographiaError {
    #[error("parse error: {0}")]
    Parse(String),

    #[error("validation error: {0}")]
    Validation(String),

    #[error("unsupported format: {0}")]
    UnsupportedFormat(String),

    #[error("serialization error: {0}")]
    Serialization(#[from] serde_json::Error),

    #[error("yaml error: {0}")]
    Yaml(#[from] serde_yaml::Error),

    #[error("io error: {0}")]
    Io(#[from] std::io::Error),
}
