//! `otg execute` — compile Intent JSON and run it read-only against Neo4j.
//!
//! Flags and environment variables match the Python entry point
//! (`python/ontographia/cli.py`). The driver is opened only after hop-range
//! and write-clause checks succeed, so a rejected Intent is not sent to Neo4j.

use std::collections::BTreeMap;
use std::fs;
use std::io::{self, IsTerminal, Read};
use std::path::{Path, PathBuf};

use clap::Args;
use ontographia_adapters::load_ontology_from_path;
use ontographia_core::emit::Dialect;
use ontographia_core::engine::Engine;
use serde_json::{Map, Value};

use crate::neo4j::{self, Neo4jSettings};
use crate::output::{self, ExecuteSuccess};
use crate::read_only::{self, DEFAULT_ROW_LIMIT, NEO4J_NOT_CONFIGURED};
use crate::safety::assert_read_only_cypher;

#[derive(Args, Debug)]
pub struct ExecuteArgs {
    /// Ontology file (default: ONTOGRAPHIA_ONTOLOGY). Format is auto-detected.
    #[arg(short, long)]
    pub ontology: Option<PathBuf>,

    /// Intent JSON file. Omit or pass - to read stdin.
    #[arg(short, long)]
    pub intent: Option<String>,

    /// Cypher dialect (default: cypher25 / ONTOGRAPHIA_DIALECT). cypher5 and gql also work.
    #[arg(short, long)]
    pub dialect: Option<String>,

    /// Print a JSON object instead of text.
    #[arg(long)]
    pub json: bool,

    /// Neo4j bolt URI (default: NEO4J_URI).
    #[arg(long)]
    pub neo4j_uri: Option<String>,

    /// Neo4j username (default: NEO4J_USERNAME or NEO4J_USER).
    #[arg(long)]
    pub neo4j_user: Option<String>,

    /// Neo4j password (default: NEO4J_PASSWORD). Prefer the env var.
    #[arg(long)]
    pub neo4j_password: Option<String>,

    /// Neo4j database name (default: NEO4J_DATABASE / driver default).
    #[arg(long)]
    pub neo4j_database: Option<String>,

    /// Max rows returned (default: 100 / ONTOGRAPHIA_MCP_ROW_LIMIT). Also caps the Cypher LIMIT.
    #[arg(long)]
    pub row_limit: Option<i64>,
}

#[derive(Debug)]
pub struct ExecuteError {
    pub code: i32,
    message: String,
}

impl ExecuteError {
    fn usage(message: impl Into<String>) -> Self {
        Self {
            code: 2,
            message: message.into(),
        }
    }

    fn fail(message: impl Into<String>) -> Self {
        Self {
            code: 1,
            message: message.into(),
        }
    }
}

impl std::fmt::Display for ExecuteError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message)
    }
}

impl std::error::Error for ExecuteError {}

pub(crate) trait EnvGet {
    fn get(&self, key: &str) -> Option<String>;
}

struct ProcessEnv;

impl EnvGet for ProcessEnv {
    fn get(&self, key: &str) -> Option<String> {
        std::env::var(key).ok().filter(|value| !value.is_empty())
    }
}

pub(crate) trait Neo4jConnector {
    fn execute(
        &self,
        settings: &Neo4jSettings,
        query: &str,
        params: &Map<String, Value>,
        row_limit: i64,
    ) -> Result<Vec<BTreeMap<String, Value>>, String>;
}

struct RealConnector;

impl Neo4jConnector for RealConnector {
    fn execute(
        &self,
        settings: &Neo4jSettings,
        query: &str,
        params: &Map<String, Value>,
        row_limit: i64,
    ) -> Result<Vec<BTreeMap<String, Value>>, String> {
        neo4j::execute_read(settings, query, params, row_limit)
    }
}

pub fn run(args: ExecuteArgs) -> Result<(), ExecuteError> {
    let success = run_with(&args, &ProcessEnv, &RealConnector)?;
    if args.json {
        println!(
            "{}",
            output::render_json(&success).map_err(|err| ExecuteError::fail(err.to_string()))?
        );
    } else {
        println!("{}", output::render_text(&success));
    }
    Ok(())
}

pub(crate) fn run_with(
    args: &ExecuteArgs,
    env: &dyn EnvGet,
    connector: &dyn Neo4jConnector,
) -> Result<ExecuteSuccess, ExecuteError> {
    let ontology = resolve_ontology(args, env)?;
    let intent = load_intent(args.intent.as_deref())?;
    let dialect = resolve_dialect(args.dialect.as_deref(), env)?;
    let row_limit = resolve_row_limit(args.row_limit, env)?;
    let settings = resolve_neo4j(args, env)?;

    let model = load_ontology_from_path(&ontology)
        .map_err(|err| ExecuteError::fail(format!("failed to load ontology: {err}")))?;
    let engine = Engine::new(model);

    let Some(settings) = settings else {
        return Err(ExecuteError::usage(NEO4J_NOT_CONFIGURED));
    };

    read_only::assert_execute_hop_policy(&intent).map_err(ExecuteError::from_guard)?;
    let bounded = read_only::intent_with_server_limit(&intent, row_limit);
    let emitted = engine
        .build_from_json(&bounded, dialect)
        .map_err(|err| ExecuteError::fail(err.to_string()))?;
    assert_read_only_cypher(&emitted.query).map_err(ExecuteError::from_guard)?;

    let params =
        serde_json::to_value(&emitted.params).map_err(|err| ExecuteError::fail(err.to_string()))?;
    let empty = Map::new();
    let params_obj = params.as_object().unwrap_or(&empty);
    let rows = connector
        .execute(&settings, &emitted.query, params_obj, row_limit)
        .map_err(|err| ExecuteError::fail(redact(&err, &settings.password)))?;
    let row_count = rows.len();
    Ok(ExecuteSuccess {
        query: emitted.query,
        params,
        rows,
        row_count,
        row_limit,
        truncated: row_count as i64 >= row_limit,
    })
}

impl ExecuteError {
    fn from_guard(err: crate::safety::GuardError) -> Self {
        Self::fail(err.message)
    }
}

fn resolve_ontology(args: &ExecuteArgs, env: &dyn EnvGet) -> Result<PathBuf, ExecuteError> {
    let paths = if let Some(path) = &args.ontology {
        vec![path.clone()]
    } else {
        match env.get("ONTOGRAPHIA_ONTOLOGY") {
            Some(raw) => std::env::split_paths(&raw)
                .filter(|path| !path.as_os_str().is_empty())
                .collect(),
            None => Vec::new(),
        }
    };
    if paths.is_empty() {
        return Err(ExecuteError::usage(
            "ontology path required (--ontology PATH or ONTOGRAPHIA_ONTOLOGY)",
        ));
    }
    if paths.len() > 1 {
        return Err(ExecuteError::usage(format!(
            "multiple ontology paths are not supported; pass a single file (got {}).",
            paths.len()
        )));
    }
    let path = paths.into_iter().next().expect("non-empty path list");
    if !path.is_file() {
        return Err(ExecuteError::usage(format!(
            "ontology file not found: {}",
            path.display()
        )));
    }
    Ok(path)
}

fn load_intent(spec: Option<&str>) -> Result<Value, ExecuteError> {
    let stdin_is_tty = io::stdin().is_terminal();
    load_intent_with(spec, stdin_is_tty, read_stdin)
}

fn read_stdin() -> Result<String, ExecuteError> {
    let mut buf = String::new();
    io::stdin()
        .read_to_string(&mut buf)
        .map_err(|err| ExecuteError::fail(format!("failed to read intent from stdin: {err}")))?;
    Ok(buf)
}

fn load_intent_with(
    spec: Option<&str>,
    stdin_is_tty: bool,
    read_stdin: impl FnOnce() -> Result<String, ExecuteError>,
) -> Result<Value, ExecuteError> {
    let text = match spec {
        None | Some("-") => {
            if spec.is_none() && stdin_is_tty {
                return Err(ExecuteError::usage(
                    "pass --intent PATH or pipe Intent JSON on stdin",
                ));
            }
            read_stdin()?
        }
        Some(path) => {
            if !Path::new(path).is_file() {
                return Err(ExecuteError::usage(format!(
                    "intent file not found: {path}"
                )));
            }
            fs::read_to_string(path)
                .map_err(|err| ExecuteError::fail(format!("failed to read intent: {err}")))?
        }
    };
    let parsed: Value = serde_json::from_str(&text)
        .map_err(|err| ExecuteError::usage(format!("intent must be a JSON object: {err}")))?;
    if !parsed.is_object() {
        return Err(ExecuteError::usage("intent JSON must be an object"));
    }
    Ok(parsed)
}

fn resolve_dialect(flag: Option<&str>, env: &dyn EnvGet) -> Result<Dialect, ExecuteError> {
    let name = flag
        .map(str::to_string)
        .or_else(|| env.get("ONTOGRAPHIA_DIALECT"))
        .unwrap_or_else(|| "cypher25".to_string());
    name.parse::<Dialect>().map_err(ExecuteError::usage)
}

fn resolve_row_limit(flag: Option<i64>, env: &dyn EnvGet) -> Result<i64, ExecuteError> {
    let requested = if let Some(limit) = flag {
        limit
    } else if let Some(raw) = env.get("ONTOGRAPHIA_MCP_ROW_LIMIT") {
        raw.parse::<i64>().map_err(|_| {
            ExecuteError::usage(format!(
                "configuration error: invalid ONTOGRAPHIA_MCP_ROW_LIMIT '{raw}'"
            ))
        })?
    } else {
        DEFAULT_ROW_LIMIT
    };
    Ok(requested.max(0))
}

fn resolve_neo4j(
    args: &ExecuteArgs,
    env: &dyn EnvGet,
) -> Result<Option<Neo4jSettings>, ExecuteError> {
    let uri = nonempty(args.neo4j_uri.clone()).or_else(|| env.get("NEO4J_URI"));
    let username = nonempty(args.neo4j_user.clone())
        .or_else(|| env.get("NEO4J_USERNAME"))
        .or_else(|| env.get("NEO4J_USER"));
    let password = nonempty(args.neo4j_password.clone()).or_else(|| env.get("NEO4J_PASSWORD"));
    let database = nonempty(args.neo4j_database.clone()).or_else(|| env.get("NEO4J_DATABASE"));
    Ok(match (uri, username, password) {
        (Some(uri), Some(username), Some(password)) => Some(Neo4jSettings {
            uri,
            username,
            password,
            database,
        }),
        _ => None,
    })
}

fn nonempty(value: Option<String>) -> Option<String> {
    value.filter(|text| !text.is_empty())
}

fn redact(message: &str, secret: &str) -> String {
    if secret.is_empty() {
        message.to_string()
    } else {
        message.replace(secret, "***")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    fn examples() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../examples")
    }

    fn args_for(intent: &str) -> ExecuteArgs {
        ExecuteArgs {
            ontology: Some(examples().join("manufacturing.native.yaml")),
            intent: Some(intent.to_string()),
            dialect: None,
            json: false,
            neo4j_uri: Some("bolt://127.0.0.1:7687".to_string()),
            neo4j_user: Some("neo4j".to_string()),
            neo4j_password: Some("secret".to_string()),
            neo4j_database: None,
            row_limit: Some(5),
        }
    }

    struct MapEnv {
        vars: BTreeMap<String, String>,
    }

    impl EnvGet for MapEnv {
        fn get(&self, key: &str) -> Option<String> {
            self.vars
                .get(key)
                .filter(|value| !value.is_empty())
                .cloned()
        }
    }

    struct RecordingConnector {
        calls: Mutex<Vec<String>>,
        fail_with: Option<String>,
    }

    impl RecordingConnector {
        fn quiet() -> Self {
            Self {
                calls: Mutex::new(Vec::new()),
                fail_with: None,
            }
        }

        fn failing(message: impl Into<String>) -> Self {
            Self {
                calls: Mutex::new(Vec::new()),
                fail_with: Some(message.into()),
            }
        }
    }

    impl Neo4jConnector for RecordingConnector {
        fn execute(
            &self,
            _settings: &Neo4jSettings,
            query: &str,
            _params: &Map<String, Value>,
            _row_limit: i64,
        ) -> Result<Vec<BTreeMap<String, Value>>, String> {
            self.calls.lock().expect("lock").push(query.to_string());
            if let Some(message) = &self.fail_with {
                return Err(message.clone());
            }
            let mut row = BTreeMap::new();
            row.insert(
                "supplier_name".to_string(),
                Value::String("Acme".to_string()),
            );
            Ok(vec![row])
        }
    }

    #[test]
    fn missing_neo4j_is_usage_and_does_not_connect() {
        let mut args = args_for(examples().join("sample_intent.json").to_str().unwrap());
        args.neo4j_uri = None;
        args.neo4j_user = None;
        args.neo4j_password = None;
        let connector = RecordingConnector::quiet();
        let err = run_with(
            &args,
            &MapEnv {
                vars: BTreeMap::new(),
            },
            &connector,
        )
        .unwrap_err();
        assert_eq!(err.code, 2);
        assert!(
            err.message.contains("Neo4j is not configured"),
            "{}",
            err.message
        );
        assert!(connector.calls.lock().unwrap().is_empty());
    }

    #[test]
    fn env_supplies_uri_user_and_password() {
        let mut args = args_for(examples().join("sample_intent.json").to_str().unwrap());
        args.neo4j_uri = None;
        args.neo4j_user = None;
        args.neo4j_password = None;
        let mut vars = BTreeMap::new();
        vars.insert("NEO4J_URI".to_string(), "bolt://127.0.0.1:7687".to_string());
        vars.insert("NEO4J_USER".to_string(), "neo4j".to_string());
        vars.insert("NEO4J_PASSWORD".to_string(), "secret".to_string());
        let connector = RecordingConnector::quiet();
        let success = run_with(&args, &MapEnv { vars }, &connector).unwrap();
        assert_eq!(success.row_count, 1);
        assert_eq!(success.rows[0]["supplier_name"], "Acme");
        let query = &connector.calls.lock().unwrap()[0];
        assert!(query.contains("MATCH"));
        assert!(!query.contains("CREATE"));
        assert!(query.contains("LIMIT 5"));
    }

    #[test]
    fn wide_hop_range_is_rejected_before_the_driver() {
        let path = std::env::temp_dir().join(format!(
            "ontographia-wide-hops-{}-{}.json",
            std::process::id(),
            "execute"
        ));
        let intent = serde_json::json!({
            "start": {"class": "Product", "alias": "product"},
            "traverse": [{
                "relationship": "has_part",
                "direction": "out",
                "to": {"class": "Part", "alias": "part"},
                "min_hops": 1,
                "max_hops": 4
            }],
            "return": [{"alias": "part"}]
        });
        fs::write(&path, serde_json::to_string(&intent).unwrap()).unwrap();
        let connector = RecordingConnector::quiet();
        let err = run_with(
            &args_for(path.to_str().unwrap()),
            &MapEnv {
                vars: BTreeMap::new(),
            },
            &connector,
        )
        .unwrap_err();
        let _ = fs::remove_file(&path);
        assert_eq!(err.code, 1);
        assert!(err.message.contains("hop range 1..4"), "{}", err.message);
        assert!(err.message.contains("single hop"), "{}", err.message);
        assert!(connector.calls.lock().unwrap().is_empty());
        assert!(!err.message.contains("secret"));
    }

    #[test]
    fn exact_one_hop_is_sent_without_a_quantifier() {
        let path = std::env::temp_dir().join(format!(
            "ontographia-one-hop-{}-{}.json",
            std::process::id(),
            "execute"
        ));
        let intent = serde_json::json!({
            "start": {"class": "Product", "alias": "product"},
            "traverse": [{
                "relationship": "has_part",
                "direction": "out",
                "to": {"class": "Part", "alias": "part"},
                "min_hops": 1,
                "max_hops": 1
            }],
            "return": [{"alias": "part", "property": "part_number", "as_name": "part_number"}]
        });
        fs::write(&path, serde_json::to_string(&intent).unwrap()).unwrap();
        let connector = RecordingConnector::quiet();
        run_with(
            &args_for(path.to_str().unwrap()),
            &MapEnv {
                vars: BTreeMap::new(),
            },
            &connector,
        )
        .unwrap();
        let _ = fs::remove_file(&path);
        let query = &connector.calls.lock().unwrap()[0];
        assert!(!query.contains('*'), "{query}");
        assert!(query.contains("has_part"));
    }

    #[test]
    fn raw_cypher_intent_is_not_executed() {
        let path = std::env::temp_dir().join(format!(
            "ontographia-raw-cypher-{}-{}.json",
            std::process::id(),
            "execute"
        ));
        fs::write(&path, r#"{"query":"CREATE (n:X) RETURN n"}"#).unwrap();
        let connector = RecordingConnector::quiet();
        let err = run_with(
            &args_for(path.to_str().unwrap()),
            &MapEnv {
                vars: BTreeMap::new(),
            },
            &connector,
        )
        .unwrap_err();
        let _ = fs::remove_file(&path);
        assert_eq!(err.code, 1);
        assert!(connector.calls.lock().unwrap().is_empty());
        assert!(!err.message.contains("secret"));
    }

    #[test]
    fn driver_errors_redact_the_password() {
        let connector = RecordingConnector::failing("auth failed for secret");
        let err = run_with(
            &args_for(examples().join("sample_intent.json").to_str().unwrap()),
            &MapEnv {
                vars: BTreeMap::new(),
            },
            &connector,
        )
        .unwrap_err();
        assert_eq!(err.code, 1);
        assert!(err.message.contains("***"));
        assert!(!err.message.contains("secret"));
    }

    #[test]
    fn missing_ontology_is_usage() {
        let mut args = args_for(examples().join("sample_intent.json").to_str().unwrap());
        args.ontology = None;
        let err = run_with(
            &args,
            &MapEnv {
                vars: BTreeMap::new(),
            },
            &RecordingConnector::quiet(),
        )
        .unwrap_err();
        assert_eq!(err.code, 2);
        assert!(err.message.contains("ontology path required"));
    }

    #[test]
    fn stdin_intent_is_required_on_a_tty() {
        let err = load_intent_with(None, true, || Ok("{}".to_string())).unwrap_err();
        assert_eq!(err.code, 2);
        assert!(err.message.contains("--intent"));
    }

    #[test]
    fn stdin_intent_object_is_accepted() {
        let value = load_intent_with(Some("-"), true, || {
            Ok(r#"{"start":{"class":"Product","alias":"p"}}"#.to_string())
        })
        .unwrap();
        assert!(value.is_object());
    }

    #[test]
    fn invalid_row_limit_env_is_usage() {
        let mut vars = BTreeMap::new();
        vars.insert("ONTOGRAPHIA_MCP_ROW_LIMIT".to_string(), "lots".to_string());
        let err = resolve_row_limit(None, &MapEnv { vars }).unwrap_err();
        assert_eq!(err.code, 2);
        assert!(err.message.contains("configuration error"));
    }
}
