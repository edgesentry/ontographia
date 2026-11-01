#!/usr/bin/env bash
# Prove a consumer can link libontographia_ffi without a checkout target/release
# sitting next to the Go module.
#
# Copies bindings/go into a temporary tree that has the manufacturing ontology
# and no target/ directory, copies the shared library aside (as a Release
# archive extract would), then:
#   1. go test with only LIBRARY_PATH and LD_LIBRARY_PATH
#   2. go build of ./cmd/smoke with only CGO_LDFLAGS (-L and rpath), then run it
#      with the loader path cleared
# The link trace must not mention this checkout's target/release.
#
#   cargo build --release -p ontographia-ffi
#   bash bindings/go/scripts/smoke-module-consumer.sh

set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
root=$(cd "${script_dir}/../../.." && pwd)

case "$(uname -s)" in
  Darwin)
    lib_name="libontographia_ffi.dylib"
    loader_var="DYLD_LIBRARY_PATH"
    ;;
  Linux)
    lib_name="libontographia_ffi.so"
    loader_var="LD_LIBRARY_PATH"
    ;;
  MINGW*|MSYS*|CYGWIN*)
    lib_name="ontographia_ffi.dll"
    loader_var="PATH"
    ;;
  *)
    echo "unsupported OS $(uname -s)" >&2
    exit 1
    ;;
esac

lib_src="${root}/target/release/${lib_name}"
if [[ ! -f "${lib_src}" ]]; then
  echo "building ontographia-ffi (release)..."
  (cd "${root}" && cargo build --release -p ontographia-ffi)
fi
if [[ ! -f "${lib_src}" ]]; then
  echo "missing ${lib_src}" >&2
  exit 1
fi

tmp=$(mktemp -d)
trap 'rm -rf "${tmp}"' EXIT

extracted="${tmp}/extracted"
mkdir -p "${extracted}" "${tmp}/repo/examples" "${tmp}/repo/bindings"
cp "${lib_src}" "${extracted}/"
cp -a "${root}/bindings/go/." "${tmp}/repo/bindings/go/"
cp "${root}/examples/manufacturing.native.yaml" "${tmp}/repo/examples/"

if [[ -e "${tmp}/repo/target" ]]; then
  echo "smoke layout unexpectedly contains target/" >&2
  exit 1
fi
if grep '^#cgo ' "${tmp}/repo/bindings/go/ontographia/ontographia.go" | grep -F 'target/release'; then
  echo "default #cgo line still references target/release" >&2
  exit 1
fi

ontology="${tmp}/repo/examples/manufacturing.native.yaml"
mod_dir="${tmp}/repo/bindings/go"

if [[ "${loader_var}" == "PATH" ]]; then
  loader_value="${extracted}${PATH:+:${PATH}}"
else
  loader_value="${extracted}"
fi

echo "smoke: link via LIBRARY_PATH only"
(
  cd "${mod_dir}"
  env -u CGO_LDFLAGS \
    CGO_ENABLED=1 \
    LIBRARY_PATH="${extracted}" \
    "${loader_var}=${loader_value}" \
    GOPROXY=off \
    GOSUMDB=off \
    go test -count=1 ./...
)

echo "smoke: link via CGO_LDFLAGS rpath, run without ${loader_var}"
link_log="${tmp}/link.log"
(
  cd "${mod_dir}"
  env -u LIBRARY_PATH -u LD_LIBRARY_PATH -u DYLD_LIBRARY_PATH \
    CGO_ENABLED=1 \
    CGO_LDFLAGS="-L${extracted} -Wl,-rpath,${extracted}" \
    GOPROXY=off \
    GOSUMDB=off \
    go build -x -o "${tmp}/smoke.bin" ./cmd/smoke
) >"${link_log}" 2>&1

if grep -F "${root}/target/release" "${link_log}"; then
  echo "link trace still references ${root}/target/release" >&2
  exit 1
fi

if [[ "${lib_name}" == "ontographia_ffi.dll" ]]; then
  # The DLL is found on PATH. GNU ld does not record an rpath for it.
  PATH="${extracted}${PATH:+:${PATH}}" "${tmp}/smoke.bin" "${ontology}"
else
  (
    cd "${tmp}"
    env -u LD_LIBRARY_PATH -u DYLD_LIBRARY_PATH \
      "${tmp}/smoke.bin" "${ontology}"
  )
fi

echo "smoke: ffi-env.sh honors ONTOGRAPHIA_FFI_LIB"
(
  unset CGO_LDFLAGS LIBRARY_PATH LD_LIBRARY_PATH DYLD_LIBRARY_PATH
  export ONTOGRAPHIA_FFI_LIB="${extracted}/${lib_name}"
  # shellcheck disable=SC1091
  source "${mod_dir}/scripts/ffi-env.sh"
  case "${CGO_LDFLAGS}" in
    *"-L${extracted}"*) ;;
    *)
      echo "CGO_LDFLAGS missing -L${extracted}: ${CGO_LDFLAGS}" >&2
      exit 1
      ;;
  esac
  case "${LIBRARY_PATH}" in
    "${extracted}"*) ;;
    *)
      echo "LIBRARY_PATH=${LIBRARY_PATH}" >&2
      exit 1
      ;;
  esac
  if [[ "${CGO_LDFLAGS}" == *"${root}/target/release"* ]]; then
    echo "ffi-env pointed at the checkout target/release" >&2
    exit 1
  fi
)

echo "smoke: ffi-env.sh checkout fallback"
(
  unset ONTOGRAPHIA_FFI_LIB CGO_LDFLAGS
  # shellcheck disable=SC1091
  source "${root}/bindings/go/scripts/ffi-env.sh"
  case "${CGO_LDFLAGS}" in
    *"-L${root}/target/release"*) ;;
    *)
      echo "checkout fallback failed: ${CGO_LDFLAGS}" >&2
      exit 1
      ;;
  esac
)

echo "smoke: module consumer ok (${lib_name})"
