// Record raw and gzip sizes of the built module for the demo page and SUMMARY.
import { gzipSync } from "node:zlib";
import { readFileSync, writeFileSync } from "node:fs";

const wasmPath = new URL("../web/ontographia_wasm.wasm", import.meta.url);
const reportPath = new URL("../web/bundle-size.json", import.meta.url);

const raw = readFileSync(wasmPath);
const gzip = gzipSync(raw, { level: 9 });
const report = { raw: raw.length, gzip: gzip.length };

writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`);

const kib = (bytes) => (bytes / 1024).toFixed(1);
console.log(`ontographia_wasm.wasm  raw ${raw.length} B (${kib(raw.length)} KiB)`);
console.log(`ontographia_wasm.wasm gzip ${gzip.length} B (${kib(gzip.length)} KiB)`);
