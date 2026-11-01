import { existsSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { arch, platform } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import koffi from "koffi";

import { OntographiaError, errorMessage } from "./errors.js";
import type { BuildResult, JsonValue } from "./types.js";

const PACKAGE_NAME = "@edgesentry/ontographia";

type BuildFn = (
  ontology: Buffer,
  ontologyLen: number,
  pathHint: string | null,
  intentJson: string,
  dialect: string | null,
) => string;

let buildFn: BuildFn | undefined;

const nodeRequire = createRequire(import.meta.url);

type PrebuildSpec = {
  id: string;
  package: string;
  os: string;
  cpu: string;
  artifact: string;
  lib: string;
  libc?: string;
};

function sharedLibraryFileName(): string {
  switch (platform()) {
    case "linux":
      return "libontographia_ffi.so";
    case "darwin":
      return "libontographia_ffi.dylib";
    case "win32":
      return "ontographia_ffi.dll";
    default:
      throw new OntographiaError(
        `unsupported platform ${platform()} (${arch()})`,
      );
  }
}

function packageDirectory(): string {
  let dir = dirname(fileURLToPath(import.meta.url));
  for (let i = 0; i < 6; i++) {
    const manifest = join(dir, "package.json");
    if (existsSync(manifest)) {
      try {
        const parsed = JSON.parse(readFileSync(manifest, "utf8")) as {
          name?: string;
        };
        if (parsed.name === PACKAGE_NAME) return dir;
      } catch {
        // Keep walking; a stray package.json should not stop the search.
      }
    }
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return dirname(fileURLToPath(import.meta.url));
}

function findRepoRoot(start: string): string | undefined {
  let dir = start;
  for (let i = 0; i < 8; i++) {
    if (existsSync(join(dir, "crates", "ontographia-ffi", "Cargo.toml"))) {
      return dir;
    }
    const parent = dirname(dir);
    if (parent === dir) return undefined;
    dir = parent;
  }
  return undefined;
}

function isPrebuildSpec(value: unknown): value is PrebuildSpec {
  if (typeof value !== "object" || value === null) return false;
  const spec = value as Record<string, unknown>;
  if (
    typeof spec.id !== "string" ||
    typeof spec.package !== "string" ||
    typeof spec.os !== "string" ||
    typeof spec.cpu !== "string" ||
    typeof spec.artifact !== "string" ||
    typeof spec.lib !== "string"
  ) {
    return false;
  }
  return spec.libc === undefined || typeof spec.libc === "string";
}

/** Platform packages declared in `npm/platforms.json`. Empty when the file is absent. */
function readPrebuildCatalog(): PrebuildSpec[] {
  const manifest = join(packageDirectory(), "npm", "platforms.json");
  if (!existsSync(manifest)) return [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(readFileSync(manifest, "utf8")) as unknown;
  } catch (err) {
    throw new OntographiaError(
      `failed to read prebuild catalog ${manifest}: ${errorMessage(err)}`,
    );
  }
  const platforms = (parsed as { platforms?: unknown }).platforms;
  if (!Array.isArray(platforms)) {
    throw new OntographiaError(
      `prebuild catalog ${manifest} is missing a platforms array`,
    );
  }
  return platforms.map((item, index) => {
    if (!isPrebuildSpec(item)) {
      throw new OntographiaError(
        `prebuild catalog ${manifest} platforms[${index}] is invalid`,
      );
    }
    return item;
  });
}

function currentPrebuild(): PrebuildSpec | undefined {
  const id = `${platform()}-${arch()}`;
  return readPrebuildCatalog().find((item) => item.id === id);
}

/**
 * Installed `@edgesentry/ontographia-<platform>` package, when npm selected one.
 * `require.resolve` covers a hoisted install. The path under this package covers
 * a nested `node_modules` before the package is linked.
 */
function bundledPrebuildCandidates(): string[] {
  const spec = currentPrebuild();
  if (!spec) return [];
  const paths: string[] = [];
  try {
    paths.push(nodeRequire.resolve(spec.package));
  } catch {
    // Not installed: git checkout, unsupported host, or optional dependency skipped.
  }
  paths.push(join(packageDirectory(), "node_modules", spec.package, spec.lib));
  return paths;
}

function unique(paths: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const path of paths) {
    if (seen.has(path)) continue;
    seen.add(path);
    out.push(path);
  }
  return out;
}

/**
 * Absolute paths checked before the dynamic loader's default search path.
 *
 * `ONTOGRAPHIA_FFI_LIB` is applied by `loadLibrary` and replaces this list, so a
 * custom build overrides the npm prebuild. `ONTOGRAPHIA_FFI_DIR` is next, then
 * the platform package, then a git checkout's `target/release` and `target/debug`.
 */
export function ffiLibraryCandidates(): string[] {
  const name = sharedLibraryFileName();
  const paths: string[] = [];
  const dir = process.env.ONTOGRAPHIA_FFI_DIR;
  if (dir) paths.push(join(dir, name));
  paths.push(...bundledPrebuildCandidates());

  const roots = [findRepoRoot(packageDirectory()), findRepoRoot(process.cwd())];
  for (const root of roots) {
    if (!root) continue;
    paths.push(join(root, "target", "release", name));
    paths.push(join(root, "target", "debug", name));
  }
  return unique(paths);
}

function tryLoad(path: string): ReturnType<typeof koffi.load> {
  try {
    return koffi.load(path);
  } catch (err) {
    throw new OntographiaError(
      `failed to load ${path}: ${errorMessage(err)}`,
    );
  }
}

function loadLibrary(): ReturnType<typeof koffi.load> {
  const explicit = process.env.ONTOGRAPHIA_FFI_LIB;
  if (explicit) {
    if (!existsSync(explicit)) {
      throw new OntographiaError(
        `ONTOGRAPHIA_FFI_LIB does not exist: ${explicit}`,
      );
    }
    return tryLoad(explicit);
  }

  const candidates = ffiLibraryCandidates();
  for (const path of candidates) {
    if (existsSync(path)) return tryLoad(path);
  }

  const name = sharedLibraryFileName();
  try {
    return koffi.load(name);
  } catch (err) {
    const looked = candidates.map((path) => `  ${path}`).join("\n");
    const supported = readPrebuildCatalog()
      .map((item) => item.id)
      .join(", ");
    throw new OntographiaError(
      `could not load ${name}. \`npm install @edgesentry/ontographia\` ships a prebuilt for: ${supported || "(catalog missing)"}. ` +
        `For a custom or dev build set ONTOGRAPHIA_FFI_LIB, or from a git checkout run \`cargo build --release -p ontographia-ffi\`.\n` +
        `Looked in:\n${looked}\nLoader error: ${errorMessage(err)}`,
    );
  }
}

function getBuildFn(): BuildFn {
  if (buildFn) return buildFn;
  const lib = loadLibrary();
  // Rust allocates the result with its global allocator. Free it with
  // ontographia_free_string — not libc free.
  const freeString = lib.func("void ontographia_free_string(void *s)");
  const ownedString = koffi.disposable("OntographiaString", "str", freeString);
  const fn = lib.func("ontographia_build_cypher_from_json", ownedString, [
    "uint8_t *",
    "size_t",
    "str",
    "str",
    "str",
  ]);
  buildFn = (ontology, ontologyLen, pathHint, intentJson, dialect) => {
    const raw: unknown = fn(ontology, ontologyLen, pathHint, intentJson, dialect);
    if (typeof raw !== "string") {
      throw new OntographiaError(
        "ontographia_build_cypher_from_json returned a non-string",
      );
    }
    return raw;
  };
  return buildFn;
}

function isParams(value: unknown): value is Record<string, JsonValue> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseFfiPayload(raw: string): BuildResult {
  let payload: { query?: unknown; params?: unknown; error?: unknown };
  try {
    payload = JSON.parse(raw) as {
      query?: unknown;
      params?: unknown;
      error?: unknown;
    };
  } catch (err) {
    throw new OntographiaError(
      `failed to parse FFI response: ${errorMessage(err)}`,
    );
  }
  if (typeof payload.error === "string" && payload.error.length > 0) {
    throw new OntographiaError(payload.error);
  }
  if (typeof payload.query !== "string" || !isParams(payload.params)) {
    throw new OntographiaError(`unexpected FFI response: ${raw}`);
  }
  return { query: payload.query, params: payload.params };
}

export function toOntologyBuffer(ontology: Uint8Array | string): Buffer {
  if (typeof ontology === "string") return Buffer.from(ontology, "utf8");
  return Buffer.from(ontology);
}

/**
 * Compile ontology bytes plus Intent JSON through `ontographia_build_cypher_from_json`.
 * Query text is produced only by the Rust engine.
 */
export function invokeBuild(
  ontology: Buffer,
  intentJson: string,
  dialect: string,
  ontologyPathHint: string | null,
): BuildResult {
  const raw = getBuildFn()(
    ontology,
    ontology.length,
    ontologyPathHint,
    intentJson,
    dialect,
  );
  return parseFfiPayload(raw);
}
