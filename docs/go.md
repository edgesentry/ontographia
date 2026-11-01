# Go

Go bindings wrap the stable C ABI in `ontographia-ffi` via cgo. Use them when you need Ontographia from a Go service without embedding the Rust runtime directly.

## Requirements

- Go **1.22+**
- A matching `libontographia_ffi` shared library (GitHub Release archive, or `cargo build --release -p ontographia-ffi` from a checkout)
- cgo (`CGO_ENABLED=1`). On Windows, cgo uses MinGW gcc (`gcc` on `PATH`).

## Quickstart (released library)

`v0.1.8` of the module still passes `-L${SRCDIR}/../../../target/release` on the cgo link line. That directory exists only in a git checkout, so `go build` from the module cache fails (`search path ... not found`, `library 'ontographia_ffi' not found`) unless you override the link and then set `DYLD_LIBRARY_PATH` because the recorded rpath is the missing checkout path.

The module on `main` does not add that path. `go build` uses `-lontographia_ffi` (Windows: `-l:ontographia_ffi.dll`) and finds the library through `LIBRARY_PATH` and `CGO_LDFLAGS`. The next `bindings/go/vX.Y.Z` tag is what publishes this link line. It does not rewrite `v0.1.8` already on the proxy. Until that tag, build this tree (or a commit that contains it), not `@v0.1.8`.

The shared library and the module should be the same version. The archive names below are the **v0.1.8** Release assets, which match the current FFI.

### 1. Go module

From this tree the import path is unchanged:

```bash
# After the next tag. v0.1.8 still has the checkout-only -L path.
go get github.com/edgesentry/ontographia/bindings/go@v0.1.8
```

### 2. FFI shared library

Pre-built libraries are attached to [GitHub Releases](https://github.com/edgesentry/ontographia/releases):

| Archive | Platform | Library file inside the archive |
|---------|----------|----------------------------------|
| `libontographia_ffi-0.1.8-linux-x86_64.tar.gz` | Linux x86_64 | `libontographia_ffi.so` |
| `libontographia_ffi-0.1.8-linux-arm64.tar.gz` | Linux arm64 (aarch64) | `libontographia_ffi.so` |
| `libontographia_ffi-0.1.8-macos-arm64.tar.gz` | macOS Apple Silicon | `libontographia_ffi.dylib` |
| `libontographia_ffi-0.1.8-windows-x86_64.tar.gz` | Windows x86_64 | `ontographia_ffi.dll` |

```bash
tar -xzf libontographia_ffi-0.1.8-linux-x86_64.tar.gz
# creates ./libontographia_ffi-0.1.8-linux-x86_64/libontographia_ffi.so
```

musl/Alpine, macOS Intel, and Windows arm64 are not built.

cgo does not expand `ONTOGRAPHIA_FFI_LIB` inside `#cgo` lines. The C compiler searches `LIBRARY_PATH` and any `-L` directory in `CGO_LDFLAGS`. Set those to the **directory** that contains the shared library. `ONTOGRAPHIA_FFI_LIB` is the same file-or-directory value the TypeScript loader accepts; `bindings/go/scripts/ffi-env.sh` (and `ffi-env.ps1`) copies it into the linker variables.

`CGO_LDFLAGS` may also record an rpath (`-Wl,-rpath,<dir>`) so the finished binary loads the library without `LD_LIBRARY_PATH` or `DYLD_LIBRARY_PATH`. Linux binaries from this module also record `$ORIGIN`, so placing `libontographia_ffi.so` next to the executable works without a loader variable.

Paths must not contain spaces or commas (the cgo linker allowlist rejects commas, and `CGO_LDFLAGS` is split on spaces).

#### Linux x86_64 and Linux arm64

```bash
export ONTOGRAPHIA_FFI_LIB="$PWD/libontographia_ffi-0.1.8-linux-x86_64/libontographia_ffi.so"
DIR="$(dirname "$ONTOGRAPHIA_FFI_LIB")"
export CGO_ENABLED=1
export CGO_LDFLAGS="-L${DIR} -Wl,-rpath,${DIR}"
export LIBRARY_PATH="${DIR}${LIBRARY_PATH:+:$LIBRARY_PATH}"
export LD_LIBRARY_PATH="${DIR}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
```

`LIBRARY_PATH` plus `LD_LIBRARY_PATH` is enough if you leave `CGO_LDFLAGS` unset: the first is link search, the second is the loader. The `CGO_LDFLAGS` rpath is what lets you drop `LD_LIBRARY_PATH` when you run the binary.

Installing the `.so` into `/usr/local/lib` and running `ldconfig` puts it on the default link and loader paths. Then `go build` needs no extra variables.

#### macOS arm64

```bash
export ONTOGRAPHIA_FFI_LIB="$PWD/libontographia_ffi-0.1.8-macos-arm64/libontographia_ffi.dylib"
DIR="$(dirname "$ONTOGRAPHIA_FFI_LIB")"
export CGO_ENABLED=1
export CGO_LDFLAGS="-L${DIR} -Wl,-rpath,${DIR}"
export LIBRARY_PATH="${DIR}${LIBRARY_PATH:+:$LIBRARY_PATH}"
export DYLD_LIBRARY_PATH="${DIR}${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
```

The dylib's install name is `@rpath/libontographia_ffi.dylib`. `DYLD_LIBRARY_PATH` finds it at run time. `-Wl,-rpath,${DIR}` records that directory in the binary so `DYLD_LIBRARY_PATH` is unnecessary afterwards. Go's cgo allowlist rejects `-rpath,@executable_path`, so do not put that flag in `#cgo` or in `CGO_LDFLAGS` unless `CGO_LDFLAGS_ALLOW` is set.

#### Windows x86_64

MinGW gcc (the usual cgo toolchain) links `ontographia_ffi.dll` by exact name (`-l:ontographia_ffi.dll`). The DLL must be on `PATH` when the program runs. `LIBRARY_PATH` and `CGO_LDFLAGS=-L` are the link search.

cmd:

```bat
set DIR=C:/ontographia/libontographia_ffi-0.1.8-windows-x86_64
set ONTOGRAPHIA_FFI_LIB=%DIR%/ontographia_ffi.dll
set CGO_ENABLED=1
set CGO_LDFLAGS=-L%DIR%
set LIBRARY_PATH=%DIR%
set PATH=%DIR%;%PATH%
```

`ffi-env.ps1` writes `CGO_LDFLAGS` with forward slashes. MinGW accepts those; cmd backslashes in `-L` are easy to mis-escape.

PowerShell, from a clone (or after copying `ffi-env.ps1` out of the module):

```powershell
$env:ONTOGRAPHIA_FFI_LIB = "C:\ontographia\libontographia_ffi-0.1.8-windows-x86_64\ontographia_ffi.dll"
. .\bindings\go\scripts\ffi-env.ps1
go build
```

The **v0.1.8** Windows archive contains `ontographia_ffi.dll` only. The next Release also ships `ontographia_ffi.dll.lib` (the MSVC import library) in that archive for `link.exe`. MinGW does not need the import library.

#### Short form (bash)

`ONTOGRAPHIA_FFI_LIB` may be the library file or the directory. A checkout with `target/release` already built can omit it.

```bash
export ONTOGRAPHIA_FFI_LIB="$PWD/libontographia_ffi-0.1.8-linux-x86_64/libontographia_ffi.so"
source bindings/go/scripts/ffi-env.sh
go build
```

`eval "$(bindings/go/scripts/ffi-env.sh)"` prints the same exports when you cannot source the file.

The Mac pre-release smoke links this tree the same way, against the published macOS archive, and does not pass `-tags ontographia_checkout`: [Pre-release checks](release.md#mac-workstation).

## Basic usage

Examples below use paths under `examples/` from a [git clone](https://github.com/edgesentry/ontographia). The Release FFI library is enough; a Rust toolchain is not, once the variables above are set.

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

`bindings/go/cmd/smoke` is the same call with a pass/fail check. Pass the ontology path. `bindings/go/scripts/smoke-module-consumer.sh` copies the module to a temporary tree that has **no** `target/release`, points the linker at a side directory that holds only the shared library, and runs `go test` plus `cmd/smoke`. CI runs that script.

```bash
cargo build --release -p ontographia-ffi
bash bindings/go/scripts/smoke-module-consumer.sh
```

## API

| Function | Description |
|----------|-------------|
| `BuildCypherFromFiles(ontologyPath, intentJSON, dialect)` | Load ontology from disk, parse Intent JSON, return query + params |

Dialect strings: `"cypher25"`, `"cypher5"`, `"gql"`. An unknown dialect or an unknown Intent key returns an error.

## Deployment notes

- Ship `libontographia_ffi` next to your binary (Linux `$ORIGIN` rpath) or install it on the system library path.
- On macOS, record an absolute rpath with `CGO_LDFLAGS` as shown above, or set `DYLD_LIBRARY_PATH`.
- On Windows, the DLL must be next to the `.exe` or on `PATH`.
- The FFI surface is intentionally small; extend capabilities in Rust (`ontographia-core`) rather than reimplementing query logic in Go.
- For schema DDL and catalog diff, use the Rust CLI (`ontographia schema`) or call `ontographia-schema` from Rust.

## Next steps

- Pipeline overview: [Architecture](architecture.md)
- Neo4j tutorial (Python-focused execution): [Neo4j walkthrough](end-to-end-neo4j.md)

## Developing from source (contributors)

**Requirements:** Rust toolchain to build `ontographia-ffi`.

### Build FFI library

```bash
cargo build --release -p ontographia-ffi
```

That writes `target/release/libontographia_ffi.so` (Linux), `libontographia_ffi.dylib` (macOS), or `ontographia_ffi.dll` (Windows).

Two ways to link it:

```bash
# Opt-in checkout path. Does not use LIBRARY_PATH.
cd bindings/go
go test -tags ontographia_checkout ./...
```

```bash
# Same variables a published consumer sets. The script finds target/release.
source bindings/go/scripts/ffi-env.sh
cd bindings/go
go test ./...
go run ./cmd/demo
```

`-tags ontographia_checkout` adds `-L${SRCDIR}/../../../target/release` and an rpath to that directory. Leave the tag off when you are checking the module-cache link line.
