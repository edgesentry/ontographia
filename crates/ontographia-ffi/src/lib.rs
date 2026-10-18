use std::ffi::{CStr, CString};
use std::os::raw::c_char;

use ontographia_adapters::load_ontology;
use ontographia_core::emit::Dialect;
use ontographia_core::engine::Engine;

/// Build Cypher from ontology bytes and Intent JSON.
///
/// # Safety
/// `ontology_bytes` must point to `ontology_len` valid bytes.
/// `intent_json` and non-null `dialect` / `ontology_path_hint` must be valid NUL-terminated UTF-8 C strings.
/// The returned pointer must be freed with `ontographia_free_string`.
#[no_mangle]
pub unsafe extern "C" fn ontographia_build_cypher_from_json(
    ontology_bytes: *const u8,
    ontology_len: usize,
    ontology_path_hint: *const c_char,
    intent_json: *const c_char,
    dialect: *const c_char,
) -> *mut c_char {
    let result = (|| -> Result<String, String> {
        if ontology_bytes.is_null() || intent_json.is_null() {
            return Err("null pointer".into());
        }
        let ontology_slice = unsafe { std::slice::from_raw_parts(ontology_bytes, ontology_len) };
        let path_hint = if ontology_path_hint.is_null() {
            None
        } else {
            Some(
                unsafe { CStr::from_ptr(ontology_path_hint) }
                    .to_str()
                    .map_err(|e| e.to_string())?,
            )
        };
        let intent_str = unsafe { CStr::from_ptr(intent_json) }
            .to_str()
            .map_err(|e| e.to_string())?;
        let intent_json: serde_json::Value =
            serde_json::from_str(intent_str).map_err(|e| e.to_string())?;

        let dialect_str = if dialect.is_null() {
            "cypher25"
        } else {
            unsafe { CStr::from_ptr(dialect) }
                .to_str()
                .map_err(|e| e.to_string())?
        };
        let dialect = dialect_str.parse::<Dialect>()?;

        let ontology = load_ontology(ontology_slice, path_hint).map_err(|e| e.to_string())?;
        let engine = Engine::new(ontology);
        let emitted = engine
            .build_from_json(&intent_json, dialect)
            .map_err(|e| e.to_string())?;

        Ok(serde_json::json!({
            "query": emitted.query,
            "params": emitted.params,
        })
        .to_string())
    })();

    match result {
        Ok(s) => CString::new(s).unwrap().into_raw(),
        Err(e) => CString::new(format!(r#"{{"error":"{}"}}"#, e.replace('"', "'")))
            .unwrap()
            .into_raw(),
    }
}

/// Free a string returned by `ontographia_build_cypher_from_json`.
///
/// # Safety
/// `s` must be a pointer previously returned by `ontographia_build_cypher_from_json`, or null.
#[no_mangle]
pub unsafe extern "C" fn ontographia_free_string(s: *mut c_char) {
    if !s.is_null() {
        unsafe {
            let _ = CString::from_raw(s);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn build(intent: &str, dialect: Option<&str>) -> serde_json::Value {
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../examples/manufacturing.native.yaml");
        let ontology = std::fs::read(path).unwrap();
        let hint = CString::new(path).unwrap();
        let intent = CString::new(intent).unwrap();
        let dialect = dialect.map(|d| CString::new(d).unwrap());
        unsafe {
            let out = ontographia_build_cypher_from_json(
                ontology.as_ptr(),
                ontology.len(),
                hint.as_ptr(),
                intent.as_ptr(),
                dialect.as_ref().map_or(std::ptr::null(), |d| d.as_ptr()),
            );
            let s = CStr::from_ptr(out).to_str().unwrap().to_owned();
            ontographia_free_string(out);
            serde_json::from_str(&s).unwrap()
        }
    }

    const INTENT: &str = r#"{"start":{"class":"Product","alias":"p"},"return":[{"alias":"p"}]}"#;

    #[test]
    fn known_and_default_dialects() {
        assert!(build(INTENT, None)["query"].as_str().unwrap().starts_with("CYPHER 25"));
        assert!(build(INTENT, Some("cypher5"))["query"].as_str().unwrap().starts_with("CYPHER 5"));
    }

    #[test]
    fn unknown_dialect_is_error() {
        let out = build(INTENT, Some("cyhper5"));
        let err = out["error"].as_str().expect("error expected");
        assert!(err.contains("unknown dialect 'cyhper5'"), "{err}");
        assert!(out.get("query").is_none());
    }

    #[test]
    fn unknown_intent_key_is_error() {
        let intent = r#"{"start":{"class":"Product","alias":"p"},"filters":[],"return":[{"alias":"p"}]}"#;
        let out = build(intent, None);
        let err = out["error"].as_str().expect("error expected");
        assert!(err.contains("unknown field"), "{err}");
    }
}
