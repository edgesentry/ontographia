package ontographia

/*
#cgo LDFLAGS: -L${SRCDIR}/../../../target/release -lontographia_ffi
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
