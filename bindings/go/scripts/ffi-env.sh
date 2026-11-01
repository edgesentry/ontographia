#!/usr/bin/env bash
# Export cgo link and loader variables for libontographia_ffi.
#
# cgo does not expand ONTOGRAPHIA_FFI_LIB. The C compiler searches
# LIBRARY_PATH and the -L entries in CGO_LDFLAGS. This script copies
# ONTOGRAPHIA_FFI_LIB into those variables (and into the platform loader path).
#
#   export ONTOGRAPHIA_FFI_LIB=/path/to/libontographia_ffi.so   # file or directory
#   source bindings/go/scripts/ffi-env.sh
#   go build
#
# With ONTOGRAPHIA_FFI_LIB unset, a git checkout uses <repo>/target/release
# when that directory already contains the shared library.
#
# Executing the script (instead of sourcing it) prints export lines:
#
#   eval "$(bindings/go/scripts/ffi-env.sh)"

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  _ONTOGRAPHIA_FFI_ENV_SOURCED=1
else
  _ONTOGRAPHIA_FFI_ENV_SOURCED=0
fi

_ontographia_ffi_dir_ok() {
  local dir="$1"
  [[ -f "${dir}/libontographia_ffi.so" || -f "${dir}/libontographia_ffi.dylib" || -f "${dir}/ontographia_ffi.dll" ]]
}

_ontographia_ffi_abs_dir() {
  local ref="$1"
  if [[ -d "${ref}" ]]; then
    (cd "${ref}" && pwd)
    return
  fi
  if [[ -f "${ref}" ]]; then
    (cd "$(dirname "${ref}")" && pwd)
    return
  fi
  return 1
}

_ontographia_ffi_resolve_dir() {
  local script_dir root candidate
  if [[ -n "${ONTOGRAPHIA_FFI_LIB:-}" ]]; then
    if ! _ontographia_ffi_abs_dir "${ONTOGRAPHIA_FFI_LIB}"; then
      echo "ffi-env: ONTOGRAPHIA_FFI_LIB does not exist: ${ONTOGRAPHIA_FFI_LIB}" >&2
      return 1
    fi
    return
  fi
  script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
  root=$(cd "${script_dir}/../../.." && pwd)
  candidate="${root}/target/release"
  if _ontographia_ffi_dir_ok "${candidate}"; then
    printf '%s\n' "${candidate}"
    return
  fi
  echo "ffi-env: set ONTOGRAPHIA_FFI_LIB to the shared library file or the directory that contains it." >&2
  echo "ffi-env: no checkout library at ${candidate}." >&2
  return 1
}

_ontographia_ffi_prepend() {
  local current="$1"
  local entry="$2"
  local sep="$3"
  if [[ -z "${current}" ]]; then
    printf '%s' "${entry}"
  elif [[ "${sep}${current}${sep}" != *"${sep}${entry}${sep}"* ]]; then
    printf '%s' "${entry}${sep}${current}"
  else
    printf '%s' "${current}"
  fi
}

_ontographia_ffi_emit() {
  local name="$1"
  local value="$2"
  if [[ "${_ONTOGRAPHIA_FFI_ENV_SOURCED}" -eq 1 ]]; then
    export "${name}=${value}"
  else
    printf 'export %q=%q\n' "${name}" "${value}"
  fi
}

_ontographia_ffi_apply() {
  local dir uname_s link_flags path_sep
  dir=$(_ontographia_ffi_resolve_dir) || return 1
  if ! _ontographia_ffi_dir_ok "${dir}"; then
    echo "ffi-env: no libontographia_ffi.{so,dylib} or ontographia_ffi.dll in ${dir}" >&2
    return 1
  fi
  case "${dir}" in
    *[[:space:],]*)
      echo "ffi-env: library directory must not contain spaces or commas: ${dir}" >&2
      return 1
      ;;
  esac

  uname_s=$(uname -s)
  path_sep=":"
  link_flags="-L${dir} -Wl,-rpath,${dir}"
  case "${uname_s}" in
    MINGW*|MSYS*|CYGWIN*)
      path_sep=";"
      # Windows loads the DLL from PATH. GNU ld has no $ORIGIN rpath here.
      link_flags="-L${dir}"
      ;;
  esac

  if [[ -n "${CGO_LDFLAGS:-}" && "${CGO_LDFLAGS}" != *"-L${dir}"* ]]; then
    link_flags="${link_flags} ${CGO_LDFLAGS}"
  elif [[ -n "${CGO_LDFLAGS:-}" ]]; then
    link_flags="${CGO_LDFLAGS}"
  fi

  _ontographia_ffi_emit CGO_ENABLED 1
  _ontographia_ffi_emit CGO_LDFLAGS "${link_flags}"
  _ontographia_ffi_emit LIBRARY_PATH "$(_ontographia_ffi_prepend "${LIBRARY_PATH:-}" "${dir}" "${path_sep}")"

  case "${uname_s}" in
    Darwin)
      _ontographia_ffi_emit DYLD_LIBRARY_PATH "$(_ontographia_ffi_prepend "${DYLD_LIBRARY_PATH:-}" "${dir}" ":")"
      ;;
    Linux)
      _ontographia_ffi_emit LD_LIBRARY_PATH "$(_ontographia_ffi_prepend "${LD_LIBRARY_PATH:-}" "${dir}" ":")"
      ;;
    MINGW*|MSYS*|CYGWIN*)
      _ontographia_ffi_emit PATH "$(_ontographia_ffi_prepend "${PATH:-}" "${dir}" "${path_sep}")"
      ;;
    *)
      echo "ffi-env: unsupported OS ${uname_s}; set the loader path yourself" >&2
      return 1
      ;;
  esac
}

if ! _ontographia_ffi_apply; then
  if [[ "${_ONTOGRAPHIA_FFI_ENV_SOURCED}" -eq 1 ]]; then
    return 1
  fi
  exit 1
fi
