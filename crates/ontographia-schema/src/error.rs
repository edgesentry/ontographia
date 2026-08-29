use thiserror::Error;

#[derive(Debug, Error)]
pub enum SchemaError {
    #[error("serialization error: {0}")]
    Serde(#[from] serde_json::Error),
}

pub type Result<T> = std::result::Result<T, SchemaError>;
