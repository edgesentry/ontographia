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
