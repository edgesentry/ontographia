//! Write-clause deny list for Cypher that `otg execute` might send to Neo4j.
//!
//! Same rules as `python/ontographia/mcp/safety.py`: case-insensitive clause
//! and procedure matches on the query after strings and comments are removed,
//! so an identifier such as `created_at` is not treated as `CREATE`.

use regex::Regex;
use std::sync::LazyLock;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GuardError {
    pub code: &'static str,
    pub message: String,
}

impl std::fmt::Display for GuardError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message)
    }
}

struct DenyPattern {
    source: &'static str,
    regex: Regex,
}

const WRITE_SOURCES: &[&str] = &[
    r"\bCREATE\b",
    r"\bMERGE\b",
    r"\bDELETE\b",
    r"\bDETACH\b",
    r"\bSET\b",
    r"\bREMOVE\b",
    r"\bDROP\b",
    r"\bFOREACH\b",
    r"\bLOAD\s+CSV\b",
    r"\bIN\s+TRANSACTIONS\b",
    r"\bapoc\.create\b",
    r"\bapoc\.merge\b",
    r"\bapoc\.periodic\b",
    r"\bapoc\.refactor\b",
    r"\bapoc\.nodes\.delete\b",
    r"\bapoc\.cypher\.do",
    r"\bapoc\.load\b",
    r"\bapoc\.export\b",
    r"\bapoc\.import\b",
    r"\bdb\.create",
    r"\bdb\.index\.",
    r"\bdb\.constraints\.",
    r"\bdbms\.security\.",
    r"\bdbms\.set",
    r"\bgds\..*\.write\b",
    r"\bgds\..*\.mutate\b",
];

fn deny_patterns() -> &'static [DenyPattern] {
    static PATTERNS: LazyLock<Vec<DenyPattern>> = LazyLock::new(|| {
        WRITE_SOURCES
            .iter()
            .map(|source| DenyPattern {
                source,
                regex: Regex::new(&format!("(?i){source}"))
                    .unwrap_or_else(|err| panic!("deny pattern {source}: {err}")),
            })
            .collect()
    });
    PATTERNS.as_slice()
}

fn string_or_comment() -> &'static Regex {
    static RE: LazyLock<Regex> = LazyLock::new(|| {
        Regex::new(r#"(?s)'(?:\\'|[^'])*'|"(?:\\"|[^"])*"|//[^\n]*|/\*.*?\*/"#)
            .expect("string/comment pattern")
    });
    &RE
}

fn strip_strings_and_comments(cypher: &str) -> String {
    string_or_comment().replace_all(cypher, " ").into_owned()
}

struct DenyHit {
    source: &'static str,
    snippet: String,
}

fn find_write_constructs(cypher: &str) -> Vec<DenyHit> {
    let scrubbed = strip_strings_and_comments(cypher);
    let mut hits = Vec::new();
    for pattern in deny_patterns() {
        if let Some(found) = pattern.regex.find(&scrubbed) {
            let start = scrubbed.floor_char_boundary(found.start().saturating_sub(20));
            let end = scrubbed.ceil_char_boundary((found.end() + 20).min(scrubbed.len()));
            hits.push(DenyHit {
                source: pattern.source,
                snippet: scrubbed[start..end].trim().to_string(),
            });
        }
    }
    hits
}

/// Refuse Cypher that matches the write deny list.
pub fn assert_read_only_cypher(cypher: &str) -> Result<(), GuardError> {
    let hits = find_write_constructs(cypher);
    if hits.is_empty() {
        return Ok(());
    }
    let details = hits
        .iter()
        .take(5)
        .map(|hit| format!("{:?} near {:?}", hit.source, hit.snippet))
        .collect::<Vec<_>>()
        .join("; ");
    Err(GuardError {
        code: "write_rejected",
        message: format!(
            "Refusing to execute write Cypher (Ontographia is read-only). Denied constructs: {details}"
        ),
    })
}

#[cfg(test)]
mod tests {
    use super::assert_read_only_cypher;

    const READ_ONLY: &str = "\
CYPHER 25
MATCH (product:Product)-[:has_part]->(part:Part)
FILTER product.sku = $param_0
RETURN part.part_number AS part_number
LIMIT 20
";

    #[test]
    fn read_only_query_is_allowed() {
        assert_read_only_cypher(READ_ONLY).unwrap();
    }

    #[test]
    fn created_at_is_not_create() {
        assert_read_only_cypher("MATCH (n) RETURN n.created_at AS created_at").unwrap();
    }

    #[test]
    fn create_inside_a_string_is_ignored() {
        assert_read_only_cypher("MATCH (n) WHERE n.note = 'please CREATE nothing' RETURN n")
            .unwrap();
    }

    #[test]
    fn write_constructs_are_denied() {
        let samples = [
            "CREATE (n:Product {sku: 'x'})",
            "MATCH (n) MERGE (n)-[:has_part]->(p:Part)",
            "MATCH (n) DELETE n",
            "MATCH (n) DETACH DELETE n",
            "MATCH (n) SET n.name = 'x'",
            "MATCH (n) REMOVE n.name",
            "DROP CONSTRAINT foo IF EXISTS",
            "LOAD CSV FROM 'file:///x.csv' AS row RETURN row",
            "MATCH (n) CALL { WITH n CREATE (n)-[:x]->() } IN TRANSACTIONS",
            "CALL apoc.create.node(['Product'], {sku:'x'})",
            "CALL apoc.merge.node(['Product'], {sku:'x'}, {}, {})",
            "CALL apoc.periodic.iterate('MATCH (n) RETURN n', 'DELETE n', {})",
            "CALL apoc.cypher.doIt('CREATE (n)', {})",
            "CALL gds.graph.project.mutate('g', ...)",
        ];
        for cypher in samples {
            let err = assert_read_only_cypher(cypher).expect_err(cypher);
            assert_eq!(err.code, "write_rejected");
            assert!(
                err.message.contains("read-only") || err.message.contains("Refusing"),
                "{cypher}: {}",
                err.message
            );
        }
    }
}
