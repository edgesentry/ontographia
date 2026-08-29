use ontographia_adapters::load_ontology;
use ontographia_core::com::CanonicalOntology;
use ontographia_core::emit::Dialect;
use ontographia_core::engine::Engine;
use ontographia_core::intent::Intent;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

#[pyclass]
struct PyEngine {
    inner: Engine,
}

#[pymethods]
impl PyEngine {
    #[staticmethod]
    fn load(path: &str) -> PyResult<Self> {
        let bytes = std::fs::read(path).map_err(|e| PyValueError::new_err(e.to_string()))?;
        let ontology =
            load_ontology(&bytes, Some(path)).map_err(|e| PyValueError::new_err(e.to_string()))?;
        Ok(Self {
            inner: Engine::new(ontology),
        })
    }

    #[staticmethod]
    fn from_bytes(data: &[u8], path_hint: Option<&str>) -> PyResult<Self> {
        let ontology = load_ontology(data, path_hint)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        Ok(Self {
            inner: Engine::new(ontology),
        })
    }

    fn intent_json_schema(&self, py: Python<'_>) -> PyResult<PyObject> {
        let schema = self.inner.intent_json_schema();
        json_to_py(py, &schema)
    }

    #[pyo3(signature = (intent, dialect=None))]
    fn build(&self, py: Python<'_>, intent: &Bound<'_, PyAny>, dialect: Option<&str>) -> PyResult<PyObject> {
        let intent_json = py_to_json(intent)?;
        let intent: Intent = serde_json::from_value(intent_json)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        let dialect = parse_dialect(dialect);
        let emitted = self
            .inner
            .build(intent, dialect)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        let dict = PyDict::new_bound(py);
        dict.set_item("query", emitted.query)?;
        dict.set_item("params", json_to_py(py, &serde_json::to_value(&emitted.params).unwrap())?)?;
        Ok(dict.into())
    }

    fn ontology_json(&self, py: Python<'_>) -> PyResult<PyObject> {
        let value = serde_json::to_value(self.inner.ontology())
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        json_to_py(py, &value)
    }
}

fn parse_dialect(dialect: Option<&str>) -> Dialect {
    match dialect.unwrap_or("cypher25") {
        "cypher5" => Dialect::Cypher5,
        "gql" => Dialect::Gql,
        _ => Dialect::Cypher25,
    }
}

fn py_to_json(value: &Bound<'_, PyAny>) -> PyResult<serde_json::Value> {
    if let Ok(s) = value.extract::<String>() {
        return Ok(serde_json::Value::String(s));
    }
    if let Ok(i) = value.extract::<i64>() {
        return Ok(serde_json::json!(i));
    }
    if let Ok(f) = value.extract::<f64>() {
        return Ok(serde_json::json!(f));
    }
    if let Ok(b) = value.extract::<bool>() {
        return Ok(serde_json::json!(b));
    }
    if let Ok(dict) = value.downcast::<PyDict>() {
        let mut map = serde_json::Map::new();
        for (k, v) in dict.iter() {
            let key: String = k.extract()?;
            map.insert(key, py_to_json(&v)?);
        }
        return Ok(serde_json::Value::Object(map));
    }
    if let Ok(list) = value.extract::<Vec<Bound<'_, PyAny>>>() {
        let items: Result<Vec<_>, _> = list.iter().map(|v| py_to_json(v)).collect();
        return Ok(serde_json::Value::Array(items?));
    }
    Err(PyValueError::new_err("unsupported Python type for intent"))
}

fn json_to_py(py: Python<'_>, value: &serde_json::Value) -> PyResult<PyObject> {
    match value {
        serde_json::Value::Null => Ok(py.None()),
        serde_json::Value::Bool(b) => Ok(b.to_object(py)),
        serde_json::Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                Ok(i.to_object(py))
            } else if let Some(f) = n.as_f64() {
                Ok(f.to_object(py))
            } else {
                Ok(n.to_string().to_object(py))
            }
        }
        serde_json::Value::String(s) => Ok(s.to_object(py)),
        serde_json::Value::Array(arr) => {
            let list = pyo3::types::PyList::empty_bound(py);
            for item in arr {
                list.append(json_to_py(py, item)?)?;
            }
            Ok(list.into())
        }
        serde_json::Value::Object(map) => {
            let dict = PyDict::new_bound(py);
            for (k, v) in map {
                dict.set_item(k, json_to_py(py, v)?)?;
            }
            Ok(dict.into())
        }
    }
}

#[pymodule]
fn ontographia(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyEngine>()?;
    m.add("Engine", m.getattr("PyEngine")?)?;
    Ok(())
}
