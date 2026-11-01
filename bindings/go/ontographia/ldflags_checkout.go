//go:build ontographia_checkout

package ontographia

// Checkout link line for contributors. Not part of the default build:
// the module cache has no target/release next to this package.
//
//	cargo build --release -p ontographia-ffi
//	cd bindings/go && go test -tags ontographia_checkout ./...

/*
#cgo !windows LDFLAGS: -L${SRCDIR}/../../../target/release -Wl,-rpath,${SRCDIR}/../../../target/release
#cgo windows LDFLAGS: -L${SRCDIR}/../../../target/release
*/
import "C"
