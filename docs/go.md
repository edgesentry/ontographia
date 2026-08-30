# Go

Go bindings wrap the stable C ABI in `ontographia-ffi` via cgo. Use them when you need Ontographia from a Go service without embedding the Rust runtime directly.

## Requirements

- Go **1.22+**
- Rust toolchain to build `ontographia-ffi`
- Shared library on the loader path (`libontographia_ffi.so` / `.dylib` / `.dll`)

## Build FFI library

```bash
cargo build --release -p ontographia-ffi
```

Set the library path when linking or running tests:

```bash
# Linux
export LD_LIBRARY_PATH="$(pwd)/target/release"

# macOS
export DYLD_LIBRARY_PATH="$(pwd)/target/release"
```

Pre-built libraries are attached to [GitHub Releases](https://github.com/edgesentry/ontographia/releases) for tagged versions:

| Archive | Platform |
|---------|----------|
| `libontographia_ffi-{version}-linux-x86_64.tar.gz` | Linux x86_64 |
| `libontographia_ffi-{version}-linux-arm64.tar.gz` | Linux arm64 (aarch64) |
| `libontographia_ffi-{version}-macos-arm64.tar.gz` | macOS Apple Silicon |
| `libontographia_ffi-{version}-windows-x86_64.tar.gz` | Windows x86_64 |

Extract the archive and point the dynamic linker at the directory containing `libontographia_ffi.so` (or `.dylib` / `.dll`):

```bash
# Linux (x86_64 or arm64)
export LD_LIBRARY_PATH=/path/to/extracted/libontographia_ffi-*/ 
```

## Module import

```bash
go get github.com/edgesentry/ontographia/bindings/go@v0.1.1
```

From a git checkout:

```bash
cd bindings/go
go test ./...
```

## Basic usage

```go
package main

import (
	"fmt"
	"path/filepath"

	"github.com/edgesentry/ontographia/bindings/go/ontographia"
)

func main() {
	ontology := filepath.Join("examples", "manufacturing.native.yaml")
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
		panic(err)
	}
	fmt.Println(result.Query)
	fmt.Println(result.Params)
}
```

## API

| Function | Description |
|----------|-------------|
| `BuildCypherFromFiles(ontologyPath, intentJSON, dialect)` | Load ontology from disk, parse Intent JSON, return query + params |
| `BuildCypher(ontologyJSON, intentJSON, dialect)` | Same with ontology bytes/JSON already in memory |

Dialect strings: `"cypher25"`, `"cypher5"`, `"gql"`.

## Demo

```bash
cargo build --release -p ontographia-ffi
cd bindings/go
export LD_LIBRARY_PATH=../../target/release   # Linux
go run ./cmd/demo
```

## Deployment notes

- Ship `libontographia_ffi` next to your binary or install it on the system library path.
- The FFI surface is intentionally small; extend capabilities in Rust (`ontographia-core`) rather than reimplementing query logic in Go.
- For schema DDL and catalog diff, use the Rust CLI (`ontographia schema`) or call `ontographia-schema` from Rust.

## Next steps

- Pipeline overview: [Architecture](architecture.md)
- Neo4j tutorial (Python-focused execution): [Neo4j walkthrough](end-to-end-neo4j.md)
