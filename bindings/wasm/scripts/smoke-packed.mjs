#!/usr/bin/env node
// Pack, install, and load the npm tarball in a clean directory, then compile
// the fixed PLM Intents with the installed package. No koffi, no native library,
// no server.
//
//   node bindings/wasm/scripts/smoke-packed.mjs
//   node bindings/wasm/scripts/smoke-packed.mjs --tarball path/to/package.tgz
//   node bindings/wasm/scripts/smoke-packed.mjs --keep
//
// The default path builds and packs first. This is the headless verification
// used by CI and the Release workflow.

import { execFileSync } from "node:child_process";
import {
  existsSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const wasmRoot = resolve(here, "..");
const repoRoot = resolve(wasmRoot, "..", "..");
const buildScript = join(here, "build-package.sh");

function usage() {
  console.log(`Usage: node bindings/wasm/scripts/smoke-packed.mjs [--tarball PATH] [--keep]

  --tarball PATH  Smoke an existing npm tarball instead of building one
  --keep          Leave the temporary install directory in place
`);
}

let tarball = "";
let keep = false;
const args = process.argv.slice(2);
for (let i = 0; i < args.length; i++) {
  const arg = args[i];
  if (arg === "--tarball") {
    tarball = args[++i] ?? "";
    if (!tarball) throw new Error("--tarball requires a path");
    tarball = resolve(tarball);
  } else if (arg === "--keep") {
    keep = true;
  } else if (arg === "-h" || arg === "--help") {
    usage();
    process.exit(0);
  } else {
    throw new Error(`unknown argument: ${arg}`);
  }
}

const version = execFileSync("bash", [join(repoRoot, "scripts", "workspace-version.sh")], {
  cwd: repoRoot,
  encoding: "utf8",
}).trim();

let buildDir = "";
if (!tarball) {
  buildDir = mkdtempSync(join(tmpdir(), "ontographia-wasm-build-"));
  execFileSync("bash", [buildScript, "--pack", "--out", buildDir], {
    cwd: repoRoot,
    stdio: "inherit",
  });
  tarball = join(buildDir, `edgesentry-ontographia-wasm-${version}.tgz`);
}
if (!existsSync(tarball)) {
  throw new Error(`tarball not found: ${tarball}`);
}

const work = mkdtempSync(join(tmpdir(), "ontographia-wasm-smoke-"));
try {
  writeFileSync(
    join(work, "package.json"),
    `${JSON.stringify({ name: "ontographia-wasm-smoke", private: true, type: "module" }, null, 2)}\n`,
  );
  mkdirSync(join(work, "node_modules"), { recursive: true });

  console.log(`installing ${tarball}`);
  execFileSync(
    "npm",
    ["install", "--no-save", "--ignore-scripts", "--no-audit", "--no-fund", tarball],
    { cwd: work, stdio: "inherit" },
  );

  const smoke = join(work, "smoke.mjs");
  writeFileSync(
    smoke,
    `import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { loadOntographia } from "@edgesentry/ontographia-wasm";

const repoRoot = process.argv[2];
const expectedVersion = process.argv[3];
const entry = fileURLToPath(import.meta.resolve("@edgesentry/ontographia-wasm"));
const packageDir = dirname(entry);
const manifest = JSON.parse(readFileSync(join(packageDir, "package.json"), "utf8"));

if (manifest.name !== "@edgesentry/ontographia-wasm") {
  throw new Error("unexpected package name: " + manifest.name);
}
if (manifest.version !== expectedVersion) {
  throw new Error("package version " + manifest.version + " != workspace " + expectedVersion);
}
for (const file of ["ontographia_wasm.wasm", "index.js", "index.d.ts", "README.md", "LICENSE"]) {
  const path = join(packageDir, file);
  if (!readFileSync(path).length) throw new Error("empty or missing " + file);
}

const wasm = readFileSync(join(packageDir, "ontographia_wasm.wasm"));
const ontology = readFileSync(join(repoRoot, "examples/plm/plm.native.yaml"));
const chips = JSON.parse(readFileSync(join(repoRoot, "examples/plm/chips.json"), "utf8"));
const engine = await loadOntographia(wasm);

if (engine.abiVersion !== 1) throw new Error("unexpected ABI version " + engine.abiVersion);
if (chips.length === 0) throw new Error("no PLM chips found");

for (const chip of chips) {
  const intent = JSON.parse(readFileSync(join(repoRoot, chip.intent_path), "utf8"));
  const result = engine.buildCypher(ontology, intent, {
    dialect: "cypher25",
    ontologyPathHint: "plm.native.yaml",
  });
  if (typeof result.query !== "string" || result.query.trim().length === 0) {
    throw new Error(chip.chip_id + ": empty query");
  }
  if (!result.query.startsWith("CYPHER 25")) {
    throw new Error(chip.chip_id + ": expected Cypher 25, got " + JSON.stringify(result.query.slice(0, 40)));
  }
  if (typeof result.params !== "object" || result.params === null) {
    throw new Error(chip.chip_id + ": expected a params object");
  }
  console.log("- " + chip.chip_id + ": " + result.query.split("\\n")[0] + " (" + Object.keys(result.params).length + " params)");
}

const notExistsOntology = readFileSync(join(repoRoot, "examples/part_usage.native.yaml"));
const notExistsIntent = JSON.parse(readFileSync(join(repoRoot, "examples/part_usage_not_exists.json"), "utf8"));
const notExists = engine.buildCypher(notExistsOntology, notExistsIntent, {
  dialect: "cypher25",
  ontologyPathHint: "part_usage.native.yaml",
});
const expectedQuery = [
  "CYPHER 25",
  "MATCH (part:Part)",
  "FILTER part.category_slug = \\$param_0 AND NOT EXISTS { MATCH (u:Usage)-[:USES_ITEM]->(part) FILTER u.match_method = \\$param_1 }",
  "RETURN part.name AS part",
  "LIMIT 200",
].join("\\n");
if (notExists.query !== expectedQuery) {
  throw new Error("not_exists: unexpected query " + JSON.stringify(notExists.query));
}
const expectedNotExistsParams = { param_0: "fasteners-and-hardware", param_1: "exact" };
const actualNotExistsParams = notExists.params ?? {};
const actualKeys = Object.keys(actualNotExistsParams).sort();
const expectedKeys = Object.keys(expectedNotExistsParams).sort();
if (JSON.stringify(actualKeys) !== JSON.stringify(expectedKeys)) {
  throw new Error("not_exists: unexpected params " + JSON.stringify(actualNotExistsParams));
}
for (const key of expectedKeys) {
  if (actualNotExistsParams[key] !== expectedNotExistsParams[key]) {
    throw new Error("not_exists: param " + key + " is " + JSON.stringify(actualNotExistsParams[key]));
  }
}
console.log("- not_exists: CYPHER 25 (" + actualKeys.length + " params)");

console.log("packed smoke ok: @edgesentry/ontographia-wasm@" + expectedVersion + ", " + chips.length + " Intents + not_exists fixture, ABI v" + engine.abiVersion);
`,
  );

  execFileSync(process.execPath, [smoke, repoRoot, version], {
    cwd: work,
    stdio: "inherit",
  });
} finally {
  if (keep) {
    console.log(`kept ${work}`);
  } else {
    rmSync(work, { recursive: true, force: true });
  }
  if (buildDir) rmSync(buildDir, { recursive: true, force: true });
}
