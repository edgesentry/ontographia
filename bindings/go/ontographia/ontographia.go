// Package ontographia builds parameter-bound Cypher from an ontology file and
// Intent JSON by calling libontographia_ffi.
//
// The default cgo line is -lontographia_ffi (on Windows, -l:ontographia_ffi.dll).
// It does not search a checkout-relative target/release directory, so
// `go build` against the module cache can link a GitHub Release archive.
// Point LIBRARY_PATH and CGO_LDFLAGS at the directory that contains the
// shared library. scripts/ffi-env.sh reads ONTOGRAPHIA_FFI_LIB and exports
// those variables. See the module README.
//
// Linux binaries also record an rpath of $ORIGIN so a copy of the shared
// library next to the executable is found at run time.
//
// In a git checkout, -tags ontographia_checkout adds
// -L${SRCDIR}/../../../target/release after `cargo build --release -p ontographia-ffi`.
package ontographia

/*
#cgo !windows LDFLAGS: -lontographia_ffi
#cgo windows LDFLAGS: -l:ontographia_ffi.dll
#cgo linux LDFLAGS: -Wl,-rpath,$ORIGIN
#include <stdlib.h>

extern char* ontographia_build_cypher_from_json(
    const unsigned char* ontology_bytes,
    size_t ontology_len,
    const char* ontology_path_hint,
    const char* intent_json,
    const char* dialect
);
extern void ontographia_free_string(char* s);
*/
import "C"
import (
	"encoding/json"
	"fmt"
	"os"
	"unsafe"
)

type BuildResult struct {
	Query  string                 `json:"query"`
	Params map[string]interface{} `json:"params"`
	Error  string                 `json:"error,omitempty"`
}

func BuildCypherFromFiles(ontologyPath, intentJSON, dialect string) (BuildResult, error) {
	ontologyBytes, err := os.ReadFile(ontologyPath)
	if err != nil {
		return BuildResult{}, err
	}

	cOntology := C.CBytes(ontologyBytes)
	defer C.free(cOntology)

	cPath := C.CString(ontologyPath)
	defer C.free(unsafe.Pointer(cPath))

	cIntent := C.CString(intentJSON)
	defer C.free(unsafe.Pointer(cIntent))

	cDialect := C.CString(dialect)
	defer C.free(unsafe.Pointer(cDialect))

	cResult := C.ontographia_build_cypher_from_json(
		(*C.uchar)(cOntology),
		C.size_t(len(ontologyBytes)),
		cPath,
		cIntent,
		cDialect,
	)
	defer C.ontographia_free_string(cResult)

	raw := C.GoString(cResult)
	var result BuildResult
	if err := json.Unmarshal([]byte(raw), &result); err != nil {
		return BuildResult{}, fmt.Errorf("failed to parse FFI response: %w", err)
	}
	if result.Error != "" {
		return result, fmt.Errorf("%s", result.Error)
	}
	return result, nil
}
