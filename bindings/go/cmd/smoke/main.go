// Command smoke links libontographia_ffi and compiles one manufacturing Intent.
//
// It is the module-consumer check: pass an ontology path, with the shared
// library found via LIBRARY_PATH / CGO_LDFLAGS rather than a repo-local
// target/release directory.
//
//	export ONTOGRAPHIA_FFI_LIB=/path/to/libontographia_ffi.so
//	source scripts/ffi-env.sh
//	go run ./cmd/smoke /path/to/manufacturing.native.yaml
package main

import (
	"fmt"
	"os"
	"strings"

	"github.com/edgesentry/ontographia/bindings/go/ontographia"
)

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintf(os.Stderr, "usage: smoke <ontology-path>\n")
		os.Exit(2)
	}

	intent := `{
		"start": {"class": "Product", "alias": "product"},
		"traverse": [
			{"relationship": "has_part", "direction": "out", "to": {"class": "Part", "alias": "part"}},
			{"relationship": "supplied_by", "direction": "out", "to": {"class": "Supplier", "alias": "supplier"}}
		],
		"filter": [{"alias": "product", "property": "sku", "op": "eq", "value": "SPX-100"}],
		"return": [{"alias": "supplier", "property": "name", "as_name": "supplier_name"}],
		"limit": 20
	}`

	result, err := ontographia.BuildCypherFromFiles(os.Args[1], intent, "cypher25")
	if err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}
	if !strings.HasPrefix(result.Query, "CYPHER 25") {
		fmt.Fprintf(os.Stderr, "unexpected query prefix: %q\n", result.Query)
		os.Exit(1)
	}
	if !strings.Contains(result.Query, "FILTER product.sku = $param_0") {
		fmt.Fprintf(os.Stderr, "expected bound SKU filter, got: %s\n", result.Query)
		os.Exit(1)
	}
	if result.Params["param_0"] != "SPX-100" {
		fmt.Fprintf(os.Stderr, "unexpected param_0: %#v\n", result.Params["param_0"])
		os.Exit(1)
	}
	fmt.Println("ok")
}
