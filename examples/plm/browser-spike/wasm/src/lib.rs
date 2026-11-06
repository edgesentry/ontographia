//! Minimal `wasm32-unknown-unknown` ABI for Ontographia.
//!
//! This crate does **not** reimplement any query logic. It is a thin,
//! hand-written C-style ABI over [`ontographia_adapters::load_ontology`] and
//! [`ontographia_core::engine::Engine::build_from_json`], so the same core
//! crates that power the CLI, the FFI bindings, and the Python bindings also
//! run inside a browser `WebAssembly` instance.
//!
//! Deliberately no `wasm-bindgen` / `wasm-pack`: the module has no imports and
//! exports only plain functions plus `memory`, so any static host can load it
//! with the standard `WebAssembly` API. See `../README.md` for the ABI.
//!
//! Every string crossing the boundary is UTF-8. Result buffers are laid out as
//! `[u32 little-endian payload length][payload bytes]`.

use ontographia_adapters::load_ontology;
use ontographia_core::emit::Dialect;
use ontographia_core::engine::Engine;

/// Version of the raw ABI exported by this crate.
pub const ABI_VERSION: u32 = 1;

/// Compile ontology bytes plus an Intent into a JSON envelope.
///
/// Returns `{"query": "...", "params": {...}}` on success and
/// `{"error": "..."}` on failure. Panics are caught and reported as errors so a
/// malformed input cannot trap the whole module.
pub fn build_json(
    ontology: &[u8],
    intent_json: &[u8],
    ontology_path_hint: Option<&str>,
    dialect: Option<&str>,
) -> String {
    let run = || -> Result<String, String> {
        let intent_text = std::str::from_utf8(intent_json).map_err(|e| e.to_string())?;
        let intent: serde_json::Value =
            serde_json::from_str(intent_text).map_err(|e| e.to_string())?;
        let dialect = dialect
            .unwrap_or("cypher25")
            .parse::<Dialect>()
            .map_err(|e| e.to_string())?;
        let ontology = load_ontology(ontology, ontology_path_hint).map_err(|e| e.to_string())?;
        let emitted = Engine::new(ontology)
            .build_from_json(&intent, dialect)
            .map_err(|e| e.to_string())?;
        Ok(serde_json::json!({
            "query": emitted.query,
            "params": emitted.params,
        })
        .to_string())
    };

    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(run)) {
        Ok(Ok(json)) => json,
        Ok(Err(message)) => error_json(&message),
        Err(_) => error_json("panic while building query"),
    }
}

fn error_json(message: &str) -> String {
    serde_json::json!({ "error": message }).to_string()
}

/// Copy `json` into a leaked `[len][bytes]` buffer and return its pointer.
fn into_result_buffer(json: &str) -> *mut u8 {
    let payload = json.as_bytes();
    let mut buffer = Vec::with_capacity(4 + payload.len());
    buffer.extend_from_slice(&(payload.len() as u32).to_le_bytes());
    buffer.extend_from_slice(payload);
    let mut boxed = buffer.into_boxed_slice();
    let pointer = boxed.as_mut_ptr();
    std::mem::forget(boxed);
    pointer
}

/// Raw ABI version. Bump when the buffer layout changes.
#[no_mangle]
pub extern "C" fn otg_abi_version() -> u32 {
    ABI_VERSION
}

/// Allocate `len` bytes of linear memory for an input buffer.
///
/// The returned pointer must be released with [`otg_free_input`].
#[no_mangle]
pub extern "C" fn otg_alloc(len: usize) -> *mut u8 {
    let mut buffer = vec![0u8; len];
    let pointer = buffer.as_mut_ptr();
    std::mem::forget(buffer);
    pointer
}

/// Release a buffer previously returned by [`otg_alloc`].
///
/// # Safety
/// `pointer` must come from [`otg_alloc`] with the same `len`, or be null.
#[no_mangle]
pub unsafe extern "C" fn otg_free_input(pointer: *mut u8, len: usize) {
    if pointer.is_null() {
        return;
    }
    unsafe {
        drop(Vec::from_raw_parts(pointer, len, len));
    }
}

/// Release a result buffer returned by [`otg_build`].
///
/// # Safety
/// `pointer` must be a non-null pointer returned by [`otg_build`].
#[no_mangle]
pub unsafe extern "C" fn otg_free_result(pointer: *mut u8) {
    if pointer.is_null() {
        return;
    }
    unsafe {
        let mut length_bytes = [0u8; 4];
        std::ptr::copy_nonoverlapping(pointer, length_bytes.as_mut_ptr(), 4);
        let total = 4 + u32::from_le_bytes(length_bytes) as usize;
        drop(Vec::from_raw_parts(pointer, total, total));
    }
}

/// Build Cypher from ontology bytes and Intent JSON.
///
/// Returns a `[u32 little-endian length][UTF-8 JSON]` buffer, or null when a
/// required pointer is null. The caller owns the buffer and must release it
/// with [`otg_free_result`]. `hint`/`dialect` may be null or empty.
///
/// # Safety
/// Every non-null pointer must reference `len` readable bytes of linear memory.
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub unsafe extern "C" fn otg_build(
    ontology: *const u8,
    ontology_len: usize,
    intent: *const u8,
    intent_len: usize,
    hint: *const u8,
    hint_len: usize,
    dialect: *const u8,
    dialect_len: usize,
) -> *mut u8 {
    if ontology.is_null() || intent.is_null() {
        return std::ptr::null_mut();
    }

    let read = |pointer: *const u8, len: usize| -> Option<&'static [u8]> {
        if pointer.is_null() || len == 0 {
            None
        } else {
            Some(unsafe { std::slice::from_raw_parts(pointer, len) })
        }
    };

    let ontology_bytes = unsafe { std::slice::from_raw_parts(ontology, ontology_len) };
    let intent_bytes = unsafe { std::slice::from_raw_parts(intent, intent_len) };
    let hint_text = read(hint, hint_len).and_then(|bytes| std::str::from_utf8(bytes).ok());
    let dialect_text = read(dialect, dialect_len).and_then(|bytes| std::str::from_utf8(bytes).ok());

    let json = build_json(ontology_bytes, intent_bytes, hint_text, dialect_text);
    into_result_buffer(&json)
}

#[cfg(test)]
mod tests {
    use super::*;

    const ONTOLOGY: &[u8] = include_bytes!("../../../plm.native.yaml");
    const INTENT: &[u8] = include_bytes!("../../../intents/01_affected_products.json");

    fn build(intent: &[u8], dialect: Option<&str>) -> serde_json::Value {
        let json = build_json(ONTOLOGY, intent, Some("plm.native.yaml"), dialect);
        serde_json::from_str(&json).unwrap()
    }

    #[test]
    fn plm_intent_builds_cypher25() {
        let out = build(INTENT, None);
        let query = out["query"].as_str().expect("query");
        assert!(query.starts_with("CYPHER 25"), "{query}");
        assert!(query.contains("(bracket:Part)<-[:CONTAINS]-(assembly:Assembly)"));
        assert_eq!(out["params"]["param_0"], "DEMO-BRKT-01");
    }

    #[test]
    fn dialect_is_honoured() {
        let out = build(INTENT, Some("cypher5"));
        assert!(out["query"].as_str().unwrap().starts_with("CYPHER 5"));
    }

    #[test]
    fn unknown_dialect_is_an_error_envelope() {
        let out = build(INTENT, Some("cyhper5"));
        assert!(
            out["error"].as_str().unwrap().contains("unknown dialect"),
            "{out}"
        );
        assert!(out.get("query").is_none());
    }

    #[test]
    fn malformed_intent_is_an_error_envelope() {
        let out = build(b"{\"start\":", None);
        assert!(out.get("error").is_some(), "{out}");
    }

    #[test]
    fn result_round_trip_copies_the_payload() {
        let json = "{\"query\":\"RETURN 1\"}";
        let pointer = into_result_buffer(json);
        assert!(!pointer.is_null());
        unsafe {
            let mut length_bytes = [0u8; 4];
            std::ptr::copy_nonoverlapping(pointer, length_bytes.as_mut_ptr(), 4);
            let len = u32::from_le_bytes(length_bytes) as usize;
            let payload = std::slice::from_raw_parts(pointer.add(4), len);
            assert_eq!(std::str::from_utf8(payload).unwrap(), json);
            otg_free_result(pointer);
        }
    }

    #[test]
    fn abi_version_is_exported() {
        assert_eq!(otg_abi_version(), ABI_VERSION);
    }
}
