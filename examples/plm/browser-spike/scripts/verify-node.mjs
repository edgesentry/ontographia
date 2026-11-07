#!/usr/bin/env node
// Verify the built WASM module outside the browser: load it with Node's
// WebAssembly API (no koffi, no native library) and compile every fixed PLM
// Intent through the same JavaScript loader the demo page uses.
//
// Usage:
//   node scripts/verify-node.mjs          # assertions + human summary
//   node scripts/verify-node.mjs --json   # machine-readable results
//
// This proves the module itself; the static server + browser steps are in
// ../README.md.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { loadOntographia } from "../web/ontographia-wasm.js";

const root = new URL("../../../../", import.meta.url);
const ontologyBytes = readFileSync(fileURLToPath(new URL("examples/plm/plm.native.yaml", root)));
const chips = JSON.parse(readFileSync(fileURLToPath(new URL("examples/plm/chips.json", root)), "utf8"));

const engine = await loadOntographia(
  readFileSync(fileURLToPath(new URL("../web/ontographia_wasm.wasm", import.meta.url))),
);
const results = {};

for (const chip of chips) {
  const intent = JSON.parse(
    readFileSync(fileURLToPath(new URL(chip.intent_path, root)), "utf8"),
  );
  const started = performance.now();
  const result = engine.buildCypher(ontologyBytes, intent, {
    dialect: "cypher25",
    ontologyPathHint: "plm.native.yaml",
  });
  const elapsed = performance.now() - started;

  if (typeof result.query !== "string" || !result.query.startsWith("CYPHER 25")) {
    throw new Error(`${chip.chip_id}: expected Cypher 25, got ${JSON.stringify(result.query)}`);
  }
  if (typeof result.params !== "object" || result.params === null) {
    throw new Error(`${chip.chip_id}: expected a params object`);
  }

  results[chip.chip_id] = { query: result.query, params: result.params, ms: elapsed };
}

if (process.argv.includes("--json")) {
  console.log(JSON.stringify(results, null, 2));
} else {
  console.log(`abi v${engine.abiVersion}: ${chips.length} Intents compiled in WebAssembly`);
  for (const [chipId, result] of Object.entries(results)) {
    const params = JSON.stringify(result.params);
    console.log(`- ${chipId}: ${result.ms.toFixed(2)} ms, params ${params}`);
  }
}
