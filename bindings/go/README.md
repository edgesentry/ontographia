# github.com/edgesentry/ontographia/bindings/go

cgo bindings for Ontographia. Validation and Cypher emission stay in the Rust engine. This module does not build query text itself.

Guide: [docs/go.md](../../docs/go.md).

## Module cache vs v0.1.8

`github.com/edgesentry/ontographia/bindings/go@v0.1.8` hardcodes:

```
#cgo LDFLAGS: -L${SRCDIR}/../../../target/release -lontographia_ffi -Wl,-rpath,...
```

That `target/release` directory exists only in a git checkout. `go build` from the module cache fails looking for it (`library 'ontographia_ffi' not found`). The link line in this tree does not add that path. It ships in the next `bindings/go` tag. It does not change the `v0.1.8` zip already on the proxy.

## Link a Release library

Download the matching asset from [GitHub Releases](https://github.com/edgesentry/ontographia/releases). The library version should match the module.

| Archive | Platform | File |
|---------|----------|------|
| `libontographia_ffi-0.1.8-linux-x86_64.tar.gz` | Linux x86_64 | `libontographia_ffi.so` |
| `libontographia_ffi-0.1.8-linux-arm64.tar.gz` | Linux arm64 | `libontographia_ffi.so` |
| `libontographia_ffi-0.1.8-macos-arm64.tar.gz` | macOS Apple Silicon | `libontographia_ffi.dylib` |
| `libontographia_ffi-0.1.8-windows-x86_64.tar.gz` | Windows x86_64 | `ontographia_ffi.dll` |

cgo does not expand `ONTOGRAPHIA_FFI_LIB`. The linker reads `LIBRARY_PATH` and `CGO_LDFLAGS`. `scripts/ffi-env.sh` (PowerShell: `scripts/ffi-env.ps1`) copies `ONTOGRAPHIA_FFI_LIB` into those variables. The value is the shared library file or the directory that contains it. Paths must not contain spaces or commas.

Linux x86_64 or arm64:

```bash
export ONTOGRAPHIA_FFI_LIB="$PWD/libontographia_ffi-0.1.8-linux-x86_64/libontographia_ffi.so"
DIR="$(dirname "$ONTOGRAPHIA_FFI_LIB")"
export CGO_ENABLED=1
export CGO_LDFLAGS="-L${DIR} -Wl,-rpath,${DIR}"
export LIBRARY_PATH="${DIR}${LIBRARY_PATH:+:$LIBRARY_PATH}"
export LD_LIBRARY_PATH="${DIR}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
```

macOS arm64 (install name is `@rpath/libontographia_ffi.dylib`):

```bash
export ONTOGRAPHIA_FFI_LIB="$PWD/libontographia_ffi-0.1.8-macos-arm64/libontographia_ffi.dylib"
DIR="$(dirname "$ONTOGRAPHIA_FFI_LIB")"
export CGO_ENABLED=1
export CGO_LDFLAGS="-L${DIR} -Wl,-rpath,${DIR}"
export LIBRARY_PATH="${DIR}${LIBRARY_PATH:+:$LIBRARY_PATH}"
export DYLD_LIBRARY_PATH="${DIR}${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
```

Windows x86_64 (cmd, MinGW gcc). The DLL must be on `PATH` at run time. The v0.1.8 archive contains the DLL. The next Release also includes `ontographia_ffi.dll.lib` for MSVC `link.exe`.

```bat
set DIR=C:/ontographia/libontographia_ffi-0.1.8-windows-x86_64
set ONTOGRAPHIA_FFI_LIB=%DIR%/ontographia_ffi.dll
set CGO_ENABLED=1
set CGO_LDFLAGS=-L%DIR%
set LIBRARY_PATH=%DIR%
set PATH=%DIR%;%PATH%
```

Use forward slashes in `-L`. `scripts/ffi-env.ps1` does that when you dot-source it.

`LIBRARY_PATH` alone is the link search. The loader variable (`LD_LIBRARY_PATH`, `DYLD_LIBRARY_PATH`, or Windows `PATH`) is the run search. `-Wl,-rpath` in `CGO_LDFLAGS` records the directory so Linux and macOS binaries do not need the loader variable afterwards. Linux also records `$ORIGIN` (library next to the executable).

```bash
export ONTOGRAPHIA_FFI_LIB=/path/to/libontographia_ffi.so
source scripts/ffi-env.sh
go build
```

## Checkout

```bash
cargo build --release -p ontographia-ffi
cd bindings/go
go test -tags ontographia_checkout ./...
```

The tag adds `-L` and rpath for `<repo>/target/release`. Without the tag, use `scripts/ffi-env.sh` (it finds that directory when `ONTOGRAPHIA_FFI_LIB` is unset).

```bash
bash bindings/go/scripts/smoke-module-consumer.sh
```

That smoke copies this module to a temporary tree with no `target/release` and links a side copy of the shared library.

## API

`ontographia.BuildCypherFromFiles(ontologyPath, intentJSON, dialect)`.

Dialect strings: `"cypher25"`, `"cypher5"`, `"gql"`.
