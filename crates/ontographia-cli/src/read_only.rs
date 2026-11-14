//! Read-only execute policy shared by `otg execute`.
//!
//! Variable-length hop ranges are rejected before Neo4j is contacted. `Engine::build`
//! can still emit those patterns for offline inspection; this module applies only
//! when a query would be run. The rules match `python/ontographia/mcp/read_only.py`.

use crate::safety::GuardError;
use serde_json::{json, Value};

pub const DEFAULT_ROW_LIMIT: i64 = 100;

pub const NEO4J_NOT_CONFIGURED: &str = "\
Neo4j is not configured. Set NEO4J_URI, \
NEO4J_USERNAME (or NEO4J_USER), and NEO4J_PASSWORD \
(optional NEO4J_DATABASE), or pass matching CLI flags.";

const EXECUTE_HOP: i64 = 1;

/// Reject hop ranges that read-only execute will not submit.
///
/// Allowed on each traverse step: both bounds omitted or JSON null, or both
/// exactly the integer `1`. Floats, booleans, one-sided bounds, and any other
/// pair are rejected. The same rule applies to every step of every
/// `not_exists[i].traverse` entry.
pub fn assert_execute_hop_policy(intent: &Value) -> Result<(), GuardError> {
    if let Some(steps) = intent.get("traverse").and_then(Value::as_array) {
        assert_traverse_hop_policy(steps, "")?;
    }
    let Some(entries) = intent.get("not_exists").and_then(Value::as_array) else {
        return Ok(());
    };
    for (entry_index, entry) in entries.iter().enumerate() {
        let Some(entry) = entry.as_object() else {
            continue;
        };
        let Some(steps) = entry.get("traverse").and_then(Value::as_array) else {
            continue;
        };
        assert_traverse_hop_policy(steps, &format!("not_exists[{entry_index}] "))?;
    }
    Ok(())
}

fn assert_traverse_hop_policy(steps: &[Value], location: &str) -> Result<(), GuardError> {
    for (index, step) in steps.iter().enumerate() {
        let Some(step) = step.as_object() else {
            continue;
        };
        let min_hops = step.get("min_hops").filter(|v| !v.is_null());
        let max_hops = step.get("max_hops").filter(|v| !v.is_null());
        if min_hops.is_none() && max_hops.is_none() {
            continue;
        }
        if json_exact_int(min_hops) == Some(EXECUTE_HOP)
            && json_exact_int(max_hops) == Some(EXECUTE_HOP)
        {
            continue;
        }
        return Err(GuardError {
            code: "hop_range_rejected",
            message: format!(
                "{location}traverse step {index} hop range {}..{} is not allowed on execute. \
Only a single hop may be submitted to Neo4j: omit min_hops and max_hops, or set both to 1. \
Variable-length patterns are not executed (use build_cypher to inspect them offline).",
                py_repr(min_hops),
                py_repr(max_hops),
            ),
        });
    }
    Ok(())
}

/// Copy `intent` and set `limit` to at most `server_limit`.
///
/// A missing limit becomes `server_limit`, so the emitted Cypher is not an
/// unbounded fetch that is only truncated after Neo4j returns rows.
pub fn intent_with_server_limit(intent: &Value, server_limit: i64) -> Value {
    let mut obj = intent.as_object().cloned().unwrap_or_default();
    let cypher_limit = match obj.get("limit") {
        None | Some(Value::Null) => server_limit,
        Some(value) => match py_int(value) {
            Some(parsed) => parsed.min(server_limit),
            None => server_limit,
        },
    };
    obj.insert("limit".to_string(), json!(cypher_limit));
    Value::Object(obj)
}

fn json_exact_int(value: Option<&Value>) -> Option<i64> {
    match value? {
        Value::Number(number) if number.is_i64() || number.is_u64() => number.as_i64(),
        _ => None,
    }
}

/// Python `int()` for the limit field: bools, integers, truncated floats, and
/// integer strings. Anything else is not a limit.
fn py_int(value: &Value) -> Option<i64> {
    match value {
        Value::Bool(true) => Some(1),
        Value::Bool(false) => Some(0),
        Value::Number(number) => {
            if let Some(integer) = number.as_i64() {
                Some(integer)
            } else if let Some(unsigned) = number.as_u64() {
                i64::try_from(unsigned).ok()
            } else {
                number.as_f64().and_then(|float| {
                    if float.is_finite() {
                        Some(float.trunc() as i64)
                    } else {
                        None
                    }
                })
            }
        }
        Value::String(text) => text.trim().parse().ok(),
        _ => None,
    }
}

fn py_repr(value: Option<&Value>) -> String {
    match value {
        None | Some(Value::Null) => "None".to_string(),
        Some(Value::Bool(true)) => "True".to_string(),
        Some(Value::Bool(false)) => "False".to_string(),
        Some(Value::Number(number)) => number.to_string(),
        Some(Value::String(text)) => format!("'{text}'"),
        Some(other) => other.to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::{assert_execute_hop_policy, intent_with_server_limit};
    use serde_json::json;

    fn intent(step: serde_json::Value) -> serde_json::Value {
        json!({
            "start": {"class": "Product", "alias": "product"},
            "traverse": [step],
            "return": [{"alias": "part"}],
        })
    }

    fn step(hops: serde_json::Value) -> serde_json::Value {
        let mut step = json!({
            "relationship": "has_part",
            "direction": "out",
            "to": {"class": "Part", "alias": "part"},
        });
        if let (Some(obj), Some(extra)) = (step.as_object_mut(), hops.as_object()) {
            for (key, value) in extra {
                obj.insert(key.clone(), value.clone());
            }
        }
        step
    }

    #[test]
    fn allows_omitted_and_exact_one_hop() {
        assert_execute_hop_policy(&intent(step(json!({})))).unwrap();
        assert_execute_hop_policy(&intent(step(json!({"min_hops": 1, "max_hops": 1})))).unwrap();
        assert_execute_hop_policy(&intent(step(json!({"min_hops": null, "max_hops": null}))))
            .unwrap();
    }

    #[test]
    fn rejects_ranges_other_than_one_hop() {
        let cases = [
            json!({"min_hops": 1, "max_hops": 4}),
            json!({"min_hops": 1, "max_hops": 4294967295u64}),
            json!({"min_hops": 0, "max_hops": 1}),
            json!({"min_hops": 2, "max_hops": 2}),
            json!({"min_hops": 1, "max_hops": 0}),
            json!({"max_hops": 4}),
            json!({"min_hops": 1}),
            json!({"min_hops": true, "max_hops": true}),
            json!({"min_hops": 1.0, "max_hops": 1.0}),
        ];
        for hops in cases {
            let err = assert_execute_hop_policy(&intent(step(hops.clone()))).unwrap_err();
            assert_eq!(err.code, "hop_range_rejected", "{hops}");
            assert!(err.message.contains("single hop"), "{}", err.message);
        }
    }

    #[test]
    fn reports_the_wide_step_index() {
        let intent = json!({
            "traverse": [
                {"min_hops": 1, "max_hops": 1},
                {"min_hops": 1, "max_hops": 3},
            ]
        });
        let err = assert_execute_hop_policy(&intent).unwrap_err();
        assert!(err.message.contains("traverse step 1"));
        assert!(err.message.contains("hop range 1..3"));
    }

    fn not_exists_intent(entries: serde_json::Value) -> serde_json::Value {
        json!({
            "start": {"class": "Product", "alias": "product"},
            "not_exists": entries,
            "return": [{"alias": "product"}],
        })
    }

    #[test]
    fn rejects_wide_not_exists_step_and_names_its_location() {
        let intent = not_exists_intent(json!([{
            "start": {"class": "Part", "alias": "part"},
            "traverse": [step(json!({"min_hops": 1, "max_hops": 5}))],
        }]));
        let err = assert_execute_hop_policy(&intent).unwrap_err();
        assert_eq!(err.code, "hop_range_rejected");
        assert!(
            err.message.starts_with(
                "not_exists[0] traverse step 0 hop range 1..5 is not allowed on execute."
            ),
            "{}",
            err.message
        );
        assert!(err.message.contains("single hop"), "{}", err.message);
    }

    #[test]
    fn rejects_one_sided_not_exists_step_bound() {
        let intent = not_exists_intent(json!([{
            "start": {"class": "Part", "alias": "part"},
            "traverse": [step(json!({"max_hops": 2}))],
        }]));
        let err = assert_execute_hop_policy(&intent).unwrap_err();
        assert_eq!(err.code, "hop_range_rejected");
        assert!(
            err.message
                .starts_with("not_exists[0] traverse step 0 hop range None..2"),
            "{}",
            err.message
        );
    }

    #[test]
    fn rejects_not_exists_step_in_second_entry() {
        let intent = not_exists_intent(json!([
            {
                "start": {"class": "Part", "alias": "part"},
                "traverse": [step(json!({"min_hops": 1, "max_hops": 1}))],
            },
            {
                "start": {"class": "Supplier", "alias": "supplier"},
                "traverse": [step(json!({"min_hops": 1, "max_hops": 3}))],
            },
        ]));
        let err = assert_execute_hop_policy(&intent).unwrap_err();
        assert!(
            err.message.starts_with("not_exists[1] traverse step 0"),
            "{}",
            err.message
        );
    }

    #[test]
    fn allows_not_exists_steps_that_are_a_single_hop() {
        let intent = not_exists_intent(json!([{
            "start": {"class": "Part", "alias": "part"},
            "traverse": [
                step(json!({"min_hops": 1, "max_hops": 1})),
                step(json!({})),
                step(json!({"min_hops": null, "max_hops": null})),
            ],
        }]));
        assert_execute_hop_policy(&intent).unwrap();
    }

    #[test]
    fn skips_malformed_not_exists_entries_and_steps() {
        let intent = not_exists_intent(json!([
            "not-an-object",
            {"start": {"class": "Part", "alias": "part"}, "traverse": "not-a-list"},
            {"start": {"class": "Part", "alias": "part"}, "traverse": [null, 7]},
        ]));
        assert_execute_hop_policy(&intent).unwrap();
    }

    #[test]
    fn server_limit_caps_and_fills_missing_limit() {
        let missing = json!({"start": {"class": "Product", "alias": "p"}});
        assert_eq!(intent_with_server_limit(&missing, 100)["limit"], 100);

        let wide = json!({"limit": 1000});
        assert_eq!(intent_with_server_limit(&wide, 25)["limit"], 25);

        let smaller = json!({"limit": 5});
        assert_eq!(intent_with_server_limit(&smaller, 25)["limit"], 5);

        let invalid = json!({"limit": "nope"});
        assert_eq!(intent_with_server_limit(&invalid, 25)["limit"], 25);
    }
}
