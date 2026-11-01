# Dot-source to export cgo link and loader variables for libontographia_ffi.
#
#   $env:ONTOGRAPHIA_FFI_LIB = "C:\ontographia\ontographia_ffi.dll"  # file or directory
#   . .\bindings\go\scripts\ffi-env.ps1
#   go build
#
# With ONTOGRAPHIA_FFI_LIB unset, a git checkout uses <repo>\target\release
# when that directory already contains the shared library.
# cgo does not read ONTOGRAPHIA_FFI_LIB; this script fills CGO_LDFLAGS,
# LIBRARY_PATH, LIB, and PATH.

$ErrorActionPreference = "Stop"

function Test-OntographiaFfiDir([string]$Dir) {
    return (Test-Path -LiteralPath (Join-Path $Dir "libontographia_ffi.so")) -or
        (Test-Path -LiteralPath (Join-Path $Dir "libontographia_ffi.dylib")) -or
        (Test-Path -LiteralPath (Join-Path $Dir "ontographia_ffi.dll"))
}

function Resolve-OntographiaFfiDir {
    $ref = $env:ONTOGRAPHIA_FFI_LIB
    if ([string]::IsNullOrEmpty($ref)) {
        $scriptDir = Split-Path -Parent $PSCommandPath
        $repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path
        $candidate = Join-Path $repoRoot "target\release"
        if (Test-OntographiaFfiDir $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
        throw "Set ONTOGRAPHIA_FFI_LIB to the shared library file or the directory that contains it. No checkout library at $candidate."
    }
    if (Test-Path -LiteralPath $ref -PathType Container) {
        $dir = (Resolve-Path -LiteralPath $ref).Path
    } elseif (Test-Path -LiteralPath $ref -PathType Leaf) {
        $dir = Split-Path -Parent (Resolve-Path -LiteralPath $ref).Path
    } else {
        throw "ONTOGRAPHIA_FFI_LIB does not exist: $ref"
    }
    if (-not (Test-OntographiaFfiDir $dir)) {
        throw "No libontographia_ffi shared library in $dir"
    }
    return $dir
}

$dir = Resolve-OntographiaFfiDir
if ($dir -match '[\s,]') {
    throw "Library directory must not contain spaces or commas: $dir"
}

# MinGW gcc accepts forward slashes. Backslashes in CGO_LDFLAGS are easy to mis-escape.
$dirForCgo = $dir -replace '\\', '/'

$env:CGO_ENABLED = "1"
if ([string]::IsNullOrEmpty($env:CGO_LDFLAGS)) {
    $env:CGO_LDFLAGS = "-L$dirForCgo"
} else {
    $env:CGO_LDFLAGS = "-L$dirForCgo $env:CGO_LDFLAGS"
}

if ([string]::IsNullOrEmpty($env:LIBRARY_PATH)) {
    $env:LIBRARY_PATH = $dirForCgo
} elseif ($env:LIBRARY_PATH -notlike "$dirForCgo*") {
    $env:LIBRARY_PATH = "$dirForCgo;$env:LIBRARY_PATH"
}

if ([string]::IsNullOrEmpty($env:LIB)) {
    $env:LIB = $dir
} elseif ($env:LIB -notlike "$dir*") {
    $env:LIB = "$dir;$env:LIB"
}

if ($env:PATH -notlike "$dir*") {
    $env:PATH = "$dir;$env:PATH"
}
