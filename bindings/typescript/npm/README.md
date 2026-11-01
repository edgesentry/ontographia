# npm platform packages

`platforms.json` is the catalog of prebuilt `libontographia_ffi` packages. `scripts/package-npm.mjs` reads it, copies each Release FFI archive into a staging package, and packs:

| npm package | Release artifact | Library |
|-------------|------------------|---------|
| `@edgesentry/ontographia-linux-x64` | `linux-x86_64` | `libontographia_ffi.so` (glibc) |
| `@edgesentry/ontographia-linux-arm64` | `linux-arm64` | `libontographia_ffi.so` (glibc) |
| `@edgesentry/ontographia-darwin-arm64` | `macos-arm64` | `libontographia_ffi.dylib` |
| `@edgesentry/ontographia-win32-x64` | `windows-x86_64` | `ontographia_ffi.dll` |

The native files are not committed. The Release workflow packs them. `@edgesentry/ontographia` lists these as `optionalDependencies` only in that packed manifest, so `npm ci` in this repo does not fetch them.

Publish and secrets: [docs/release.md](../../../docs/release.md).
