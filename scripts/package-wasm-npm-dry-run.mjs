#!/usr/bin/env node
// Build and pack @edgesentry/ontographia-wasm, then assert the tarball contains
// the wasm module, JS binding, TypeScript declarations, README, and LICENSE.
// Nothing is published. Used by release preflight and locally.
//
//   node scripts/package-wasm-npm-dry-run.mjs

import { execFileSync } from "node:child_process";
import {
  mkdtempSync,
  readFileSync,
  rmSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const buildScript = join(repoRoot, "bindings", "wasm", "scripts", "build-package.sh");

function usage() {
  console.log(`Usage: node scripts/package-wasm-npm-dry-run.mjs

  Builds with the pinned Rust toolchain, runs npm pack, and checks the file
  list. Does not run npm publish.
`);
}

const args = process.argv.slice(2);
for (const arg of args) {
  if (arg === "-h" || arg === "--help") {
    usage();
    process.exit(0);
  }
  throw new Error(`unknown argument: ${arg}`);
}

const version = execFileSync("bash", [join(repoRoot, "scripts", "workspace-version.sh")], {
  cwd: repoRoot,
  encoding: "utf8",
}).trim();

const work = mkdtempSync(join(tmpdir(), "ontographia-wasm-pack-"));
try {
  console.log("==> wasm npm pack dry-run (pinned toolchain, no publish)");
  const stdout = execFileSync("bash", [buildScript, "--pack", "--out", work], {
    cwd: repoRoot,
    encoding: "utf8",
  });
  process.stdout.write(stdout);

  const tarball = join(work, `edgesentry-ontographia-wasm-${version}.tgz`);
  const entries = execFileSync("tar", ["-tzf", tarball], { encoding: "utf8" })
    .split("\n")
    .filter(Boolean)
    .sort();

  const required = [
    "package/LICENSE",
    "package/README.md",
    "package/index.d.ts",
    "package/index.js",
    "package/ontographia_wasm.wasm",
    "package/package.json",
  ];
  for (const entry of required) {
    if (!entries.includes(entry)) {
      throw new Error(`${tarball} is missing ${entry}`);
    }
  }
  for (const entry of entries) {
    if (entry.startsWith("package/node_modules/") || entry.startsWith("package/src/")) {
      throw new Error(`${tarball} contains unexpected ${entry}`);
    }
  }

  const manifest = JSON.parse(
    execFileSync("tar", ["-xOzf", tarball, "package/package.json"], { encoding: "utf8" }),
  );
  if (manifest.name !== "@edgesentry/ontographia-wasm") {
    throw new Error(`packed name is ${manifest.name}`);
  }
  if (manifest.version !== version) {
    throw new Error(`packed version ${manifest.version} != workspace ${version}`);
  }
  if (!manifest.exports?.["."]?.types || !manifest.exports?.["."]?.import) {
    throw new Error("packed manifest is missing types/import exports");
  }

  const wasm = execFileSync("tar", ["-xOzf", tarball, "package/ontographia_wasm.wasm"], {
    maxBuffer: 64 * 1024 * 1024,
  });
  if (wasm.length === 0) throw new Error("packed wasm is empty");

  console.log(
    `wasm npm pack dry-run ok (@edgesentry/ontographia-wasm@${version}, wasm ${wasm.length} B, js + types + README/LICENSE, no publish)`,
  );
  console.log(`packed tarball ${tarball} (${readFileSync(tarball).length} B)`);
} finally {
  rmSync(work, { recursive: true, force: true });
}
