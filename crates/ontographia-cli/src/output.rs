//! Text and JSON rendering for `otg execute`.
//!
//! The text shape matches the Python CLI: compiled Cypher, bound parameters,
//! a column table, and a row count. Column names are sorted because the Rust
//! driver stores each record's fields in a hash map.

use serde_json::{Map, Value};
use std::collections::BTreeMap;

#[derive(Debug)]
pub struct ExecuteSuccess {
    pub query: String,
    pub params: Value,
    pub rows: Vec<BTreeMap<String, Value>>,
    pub row_count: usize,
    pub row_limit: i64,
    pub truncated: bool,
}

pub fn render_text(success: &ExecuteSuccess) -> String {
    let mut line = format!(
        "{} {}",
        success.row_count,
        if success.row_count == 1 {
            "row"
        } else {
            "rows"
        }
    );
    if success.truncated {
        line.push_str(&format!(" (truncated at {})", success.row_limit));
    }
    [
        success.query.clone(),
        render_params(&success.params),
        render_table(&success.rows),
        line,
    ]
    .join("\n\n")
}

pub fn render_json(success: &ExecuteSuccess) -> Result<String, serde_json::Error> {
    let rows: Vec<Value> = success
        .rows
        .iter()
        .map(|row| {
            let mut object = Map::new();
            for (key, value) in row {
                object.insert(key.clone(), value.clone());
            }
            Value::Object(object)
        })
        .collect();
    let payload = serde_json::json!({
        "ok": true,
        "query": success.query,
        "params": success.params,
        "rows": rows,
        "row_count": success.row_count,
        "row_limit": success.row_limit,
        "truncated": success.truncated,
    });
    serde_json::to_string_pretty(&payload)
}

fn render_params(params: &Value) -> String {
    let mut lines = vec!["params:".to_string()];
    match params.as_object() {
        Some(object) if !object.is_empty() => {
            for (key, value) in object {
                let rendered = serde_json::to_string(value).unwrap_or_else(|_| "null".to_string());
                lines.push(format!("  {key}: {rendered}"));
            }
        }
        _ => lines.push("  (none)".to_string()),
    }
    lines.join("\n")
}

fn render_table(rows: &[BTreeMap<String, Value>]) -> String {
    if rows.is_empty() {
        return "(no rows)".to_string();
    }
    let mut columns = Vec::new();
    for row in rows {
        for key in row.keys() {
            if !columns.contains(key) {
                columns.push(key.clone());
            }
        }
    }
    let rendered: Vec<Vec<String>> = rows
        .iter()
        .map(|row| {
            columns
                .iter()
                .map(|column| cell_text(row.get(column)))
                .collect()
        })
        .collect();
    let mut widths: Vec<usize> = columns.iter().map(|column| char_len(column)).collect();
    for cells in &rendered {
        for (index, cell) in cells.iter().enumerate() {
            widths[index] = widths[index].max(char_len(cell));
        }
    }
    let mut lines = Vec::with_capacity(rendered.len() + 2);
    lines.push(join_padded(&columns, &widths));
    lines.push(
        widths
            .iter()
            .map(|width| "-".repeat(*width))
            .collect::<Vec<_>>()
            .join("  "),
    );
    for cells in &rendered {
        lines.push(join_padded(cells, &widths));
    }
    lines.join("\n")
}

fn cell_text(value: Option<&Value>) -> String {
    let Some(value) = value else {
        return String::new();
    };
    let text = match value {
        Value::String(text) => text.clone(),
        other => serde_json::to_string(other).unwrap_or_else(|_| "null".to_string()),
    };
    text.replace('\n', " ")
}

fn join_padded(cells: &[impl AsRef<str>], widths: &[usize]) -> String {
    cells
        .iter()
        .enumerate()
        .map(|(index, cell)| pad(cell.as_ref(), widths[index]))
        .collect::<Vec<_>>()
        .join("  ")
}

fn pad(text: &str, width: usize) -> String {
    let extra = width.saturating_sub(char_len(text));
    format!("{text}{}", " ".repeat(extra))
}

fn char_len(text: &str) -> usize {
    text.chars().count()
}

#[cfg(test)]
mod tests {
    use super::{render_json, render_text, ExecuteSuccess};
    use serde_json::json;
    use std::collections::BTreeMap;

    fn success(rows: Vec<BTreeMap<String, serde_json::Value>>, truncated: bool) -> ExecuteSuccess {
        ExecuteSuccess {
            query: "CYPHER 25\nMATCH (n) RETURN n.name AS actor".to_string(),
            params: json!({"param_0": "The Matrix"}),
            rows: rows.clone(),
            row_count: rows.len(),
            row_limit: 100,
            truncated,
        }
    }

    #[test]
    fn text_table_matches_python_shape() {
        let mut row = BTreeMap::new();
        row.insert("actor".to_string(), json!("Keanu Reeves"));
        let text = render_text(&success(vec![row], false));
        assert!(text.contains("CYPHER 25"));
        assert!(text.contains("params:\n  param_0: \"The Matrix\""));
        // Header and rule are padded to the widest cell, same as Python ljust.
        assert!(text.contains("actor       \n------------\nKeanu Reeves"));
        assert!(text.ends_with("1 row"));
    }

    #[test]
    fn empty_rows_and_truncation() {
        let text = render_text(&success(vec![], true));
        assert!(text.contains("params:\n  param_0: \"The Matrix\""));
        assert!(text.contains("(no rows)"));
        assert!(text.ends_with("0 rows (truncated at 100)"));
    }

    #[test]
    fn json_includes_rows_and_ok() {
        let mut row = BTreeMap::new();
        row.insert("actor".to_string(), json!("Keanu Reeves"));
        let payload: serde_json::Value =
            serde_json::from_str(&render_json(&success(vec![row], false)).unwrap()).unwrap();
        assert_eq!(payload["ok"], true);
        assert_eq!(payload["row_count"], 1);
        assert_eq!(payload["rows"][0]["actor"], "Keanu Reeves");
        assert_eq!(payload["params"]["param_0"], "The Matrix");
        assert_eq!(payload["truncated"], false);
    }
}
