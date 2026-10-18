package ontographia_test

import (
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"github.com/edgesentry/ontographia/bindings/go/ontographia"
)

func repoRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(file), "../../.."))
}

func manufacturingSupplierIntent() string {
	return `{
		"start": {"class": "Product", "alias": "product"},
		"traverse": [
			{"relationship": "has_part", "direction": "out", "to": {"class": "Part", "alias": "part"}},
			{"relationship": "supplied_by", "direction": "out", "to": {"class": "Supplier", "alias": "supplier"}}
		],
		"filter": [{"alias": "product", "property": "sku", "op": "eq", "value": "SPX-100"}],
		"return": [{"alias": "supplier", "property": "name", "as_name": "supplier_name"}],
		"limit": 20
	}`
}

func TestBuildCypherFromFiles_ManufacturingNativeYAML(t *testing.T) {
	ontology := filepath.Join(repoRoot(t), "examples", "manufacturing.native.yaml")
	result, err := ontographia.BuildCypherFromFiles(ontology, manufacturingSupplierIntent(), "cypher25")
	if err != nil {
		t.Fatalf("BuildCypherFromFiles: %v", err)
	}

	if !strings.HasPrefix(result.Query, "CYPHER 25") {
		t.Fatalf("unexpected query prefix: %q", result.Query)
	}
	if !strings.Contains(result.Query, "FILTER product.sku = $param_0") {
		t.Fatalf("expected bound SKU filter, got: %s", result.Query)
	}
	if result.Params["param_0"] != "SPX-100" {
		t.Fatalf("unexpected param_0: %#v", result.Params["param_0"])
	}
}

func TestBuildCypherFromFiles_Cypher5Dialect(t *testing.T) {
	ontology := filepath.Join(repoRoot(t), "examples", "manufacturing.native.yaml")
	result, err := ontographia.BuildCypherFromFiles(ontology, manufacturingSupplierIntent(), "cypher5")
	if err != nil {
		t.Fatalf("BuildCypherFromFiles: %v", err)
	}
	if !strings.HasPrefix(result.Query, "CYPHER 5") {
		t.Fatalf("unexpected query prefix: %q", result.Query)
	}
	if !strings.Contains(result.Query, "WHERE ") {
		t.Fatalf("expected WHERE clause for cypher5, got: %s", result.Query)
	}
}

// Issue #81: unknown dialect must be an error, not a silent cypher25 fallback.
func TestBuildCypherFromFiles_UnknownDialectIsError(t *testing.T) {
	ontology := filepath.Join(repoRoot(t), "examples", "manufacturing.native.yaml")
	_, err := ontographia.BuildCypherFromFiles(ontology, manufacturingSupplierIntent(), "cyhper5")
	if err == nil {
		t.Fatal("expected error for unknown dialect")
	}
	if !strings.Contains(err.Error(), "unknown dialect 'cyhper5'") {
		t.Fatalf("unexpected error: %v", err)
	}
}

// Issue #81: unknown Intent keys must be rejected, not silently ignored.
func TestBuildCypherFromFiles_UnknownIntentKeyIsError(t *testing.T) {
	ontology := filepath.Join(repoRoot(t), "examples", "manufacturing.native.yaml")
	intent := strings.Replace(manufacturingSupplierIntent(), `"filter":`, `"filters":`, 1)
	_, err := ontographia.BuildCypherFromFiles(ontology, intent, "cypher25")
	if err == nil {
		t.Fatal("expected error for unknown Intent key")
	}
	if !strings.Contains(err.Error(), "unknown field") || !strings.Contains(err.Error(), "filters") {
		t.Fatalf("unexpected error: %v", err)
	}
}
