#!/usr/bin/env node
// Pack @edgesentry/ontographia and the four platform tarballs without publishing.
// Real FFI archives are not built during Release check (they are produced later
// by the FFI jobs). Stub archives are enough to validate tarball metadata.
// Pass --ffi-archives DIR to pack real libontographia_ffi-*-<artifact>.tar.gz
// files instead.
//
//   node scripts/package-npm-dry-run.mjs

import { execFileSync } from "node:child_process";
import {
  existsSync,
  mkdtempSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const tsRoot = join(repoRoot, "bindings", "typescript");

const PLATFORM_PACKAGES = [
  "@edgesentry/ontographia-linux-x64",
  "@edgesentry/ontographia-linux-arm64",
  "@edgesentry/ontographia-darwin-arm64",
  "@edgesentry/ontographia-win32-x64",
];

function usage() {
  console.log(`Usage: node scripts/package-npm-dry-run.mjs [--ffi-archives DIR]

  Builds bindings/typescript when dist/index.js is missing, packs tarballs, and
  checks optionalDependencies. Does not run npm publish.
`);
}

function parseArgs(argv) {
  let ffiArchives = "";
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--ffi-archives") {
      ffiArchives = argv[++i] ?? "";
      if (!ffiArchives) throw new Error("--ffi-archives requires a directory");
    } else if (arg === "-h" || arg === "--help") {
      usage();
      process.exit(0);
    } else {
      throw new Error(`unknown argument: ${arg}`);
    }
  }
  return { ffiArchives };
}

function workspaceVersion() {
  return execFileSync("bash", [join(repoRoot, "scripts", "workspace-version.sh")], {
    cwd: repoRoot,
    encoding: "utf8",
  }).trim();
}

function readCatalog() {
  const manifest = join(tsRoot, "npm", "platforms.json");
  const parsed = JSON.parse(readFileSync(manifest, "utf8"));
  if (!Array.isArray(parsed.platforms)) {
    throw new Error(`${manifest} is missing a platforms array`);
  }
  return parsed.platforms;
}

function ensureBuilt() {
  const entry = join(tsRoot, "dist", "index.js");
  if (existsSync(entry)) return;
  console.log("bindings/typescript/dist is missing; npm ci && npm run build");
  execFileSync("npm", ["ci"], { cwd: tsRoot, stdio: "inherit" });
  execFileSync("npm", ["run", "build"], { cwd: tsRoot, stdio: "inherit" });
  if (!existsSync(entry)) {
    throw new Error("npm run build did not write bindings/typescript/dist/index.js");
  }
}

function createStubArchives(platforms, dir) {
  const stage = join(dir, "stage");
  mkdirSync(stage, { recursive: true });
  for (const spec of platforms) {
    const folderName = `libontographia_ffi-0.0.0-${spec.artifact}`;
    const folder = join(stage, folderName);
    mkdirSync(folder, { recursive: true });
    writeFileSync(join(folder, spec.lib), `stub ${spec.id}\n`);
    execFileSync("tar", ["-czf", join(dir, `${folderName}.tar.gz`), "-C", stage, folderName]);
  }
  return dir;
}

function archivesCover(platforms, dir) {
  if (!dir || !existsSync(dir)) return false;
  const names = readdirSync(dir);
  return platforms.every((spec) =>
    names.some((name) => name.endsWith(`-${spec.artifact}.tar.gz`)),
  );
}

function readPackedJson(tgz) {
  const stdout = execFileSync("tar", ["-xOzf", tgz, "package/package.json"], {
    encoding: "utf8",
  });
  return JSON.parse(stdout);
}

function assertOptionalDependencies(outDir, version, platforms) {
  const mainTgz = join(outDir, `edgesentry-ontographia-${version}.tgz`);
  if (!existsSync(mainTgz)) {
    throw new Error(`main tarball is missing: ${mainTgz}`);
  }
  const main = readPackedJson(mainTgz);
  if (main.name !== "@edgesentry/ontographia") {
    throw new Error(`main tarball name is ${main.name}`);
  }
  if (main.version !== version) {
    throw new Error(`main tarball version ${main.version} != ${version}`);
  }
  const deps = main.optionalDependencies ?? {};
  const keys = Object.keys(deps);
  if (platforms.length !== PLATFORM_PACKAGES.length) {
    throw new Error(
      `platforms.json has ${platforms.length} entries; Release expects ${PLATFORM_PACKAGES.length}`,
    );
  }
  const catalogNames = platforms.map((spec) => spec.package).sort();
  const expected = [...PLATFORM_PACKAGES].sort();
  if (catalogNames.join("\n") !== expected.join("\n")) {
    throw new Error(
      `platform package names differ from the four Release packages:\n  catalog: ${catalogNames.join(", ")}\n  expected: ${expected.join(", ")}`,
    );
  }
  if (keys.length !== PLATFORM_PACKAGES.length) {
    throw new Error(
      `optionalDependencies has ${keys.length} entries, want ${PLATFORM_PACKAGES.length}: ${keys.join(", ")}`,
    );
  }
  for (const name of PLATFORM_PACKAGES) {
    if (deps[name] !== version) {
      throw new Error(`optionalDependencies[${name}] is ${deps[name] ?? "<missing>"}, want ${version}`);
    }
  }
  console.log("optionalDependencies:");
  for (const name of PLATFORM_PACKAGES) {
    console.log(`  ${name}@${deps[name]}`);
  }
}

function run() {
  const args = parseArgs(process.argv.slice(2));
  const version = workspaceVersion();
  const platforms = readCatalog();
  ensureBuilt();

  const work = mkdtempSync(join(tmpdir(), "ontographia-npm-dry-run-"));
  try {
    let archives = args.ffiArchives ? resolve(args.ffiArchives) : "";
    let mode = "ffi archives";
    if (!archivesCover(platforms, archives)) {
      if (archives) {
        throw new Error(
          `--ffi-archives ${archives} is missing a libontographia_ffi archive for one of the four platforms`,
        );
      }
      archives = createStubArchives(platforms, join(work, "archives"));
      mode = "stub FFI archives";
      console.log("FFI archives are not available in this check; packing stub libraries");
    }
    const outDir = join(work, "out");
    console.log(`==> npm pack dry-run (${mode}, no publish)`);
    execFileSync(
      process.execPath,
      [
        join(repoRoot, "scripts", "package-npm.mjs"),
        "--ffi-archives",
        archives,
        "--skip-build",
        "--out",
        outDir,
      ],
      { cwd: repoRoot, stdio: "inherit" },
    );
    assertOptionalDependencies(outDir, version, platforms);
    console.log(
      `npm pack dry-run ok (${version}, ${PLATFORM_PACKAGES.length} platform optionalDependencies, no publish)`,
    );
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
}

try {
  run();
} catch (err) {
  console.error(err instanceof Error ? err.message : String(err));
  process.exit(1);
}
