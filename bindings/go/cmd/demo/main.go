package main

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/yohei1126/ontographia/bindings/go/ontographia"
)

func main() {
	repoRoot := filepath.Clean(filepath.Join("..", "..", "..", ".."))
	ontology := filepath.Join(repoRoot, "examples", "manufacturing.native.yaml")

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

	result, err := ontographia.BuildCypherFromFiles(ontology, intent, "cypher25")
	if err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}

	fmt.Println(result.Query)
	fmt.Println(result.Params)
}
