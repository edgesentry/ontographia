#!/usr/bin/env node
// Pack @edgesentry/ontographia and the four platform packages that carry
// libontographia_ffi. The source package.json has no optionalDependencies:
// those packages are unpublished during development, and CI must `npm ci`
// without them. This script stamps the dependencies into the published manifest.
//
//   node scripts/package-npm.mjs --local --out dist/npm
//   node scripts/package-npm.mjs --ffi-archives path/to/ffi-tarballs --out dist/npm
//
// --local packs the host platform from target/release (or target/debug) plus the
// main package (optionalDependencies still lists every platform).
// --ffi-archives packs every platform. Release uses this. Each archive is the
// libontographia_ffi-<version>-<artifact>.tar.gz produced by the FFI job.

import { execFileSync } from "node:child_process";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { arch, platform } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const tsRoot = join(repoRoot, "bindings", "typescript");

function usage() {
  console.log(`Usage: node scripts/package-npm.mjs [--local | --ffi-archives DIR] [--out DIR] [--skip-build]

  --local            Pack the current OS/CPU from target/{release,debug} (default)
  --ffi-archives DIR Pack every platform from libontographia_ffi-*-<artifact>.tar.gz
  --out DIR          Tarball directory (wiped). Default: dist/npm
  --skip-build       Use the existing bindings/typescript/dist
`);
}

function parseArgs(argv) {
  let mode = "";
  let ffiArchives = "";
  let outDir = join(repoRoot, "dist", "npm");
  let skipBuild = false;
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--local") {
      mode = "local";
    } else if (arg === "--ffi-archives") {
      mode = "archives";
      ffiArchives = argv[++i] ?? "";
      if (!ffiArchives) throw new Error("--ffi-archives requires a directory");
    } else if (arg === "--out") {
      outDir = argv[++i] ?? "";
      if (!outDir) throw new Error("--out requires a directory");
    } else if (arg === "--skip-build") {
      skipBuild = true;
    } else if (arg === "-h" || arg === "--help") {
      usage();
      process.exit(0);
    } else {
      throw new Error(`unknown argument: ${arg}`);
    }
  }
  if (!mode) mode = "local";
  return { mode, ffiArchives, outDir: resolve(outDir), skipBuild };
}

function workspaceVersion() {
  const text = readFileSync(join(repoRoot, "Cargo.toml"), "utf8");
  const section = text.split("[workspace.package]")[1]?.split(/\n\[/)[0] ?? "";
  const match = section.match(/^version = "([^"]+)"/m);
  if (!match) throw new Error("Cargo.toml [workspace.package] version not found");
  return match[1];
}

function readCatalog() {
  const manifest = join(tsRoot, "npm", "platforms.json");
  const parsed = JSON.parse(readFileSync(manifest, "utf8"));
  if (!Array.isArray(parsed.platforms) || parsed.platforms.length === 0) {
    throw new Error(`${manifest} is missing a platforms array`);
  }
  const seen = new Set();
  for (const spec of parsed.platforms) {
    for (const key of ["id", "package", "os", "cpu", "artifact", "lib"]) {
      if (typeof spec[key] !== "string" || spec[key].length === 0) {
        throw new Error(`${manifest} entry is missing ${key}`);
      }
    }
    if (spec.libc !== undefined && typeof spec.libc !== "string") {
      throw new Error(`${manifest} ${spec.id} libc must be a string`);
    }
    if (!spec.package.startsWith("@edgesentry/ontographia-")) {
      throw new Error(`${spec.package} must be a platform package name`);
    }
    if (seen.has(spec.id) || seen.has(spec.package) || seen.has(spec.artifact)) {
      throw new Error(`duplicate catalog entry ${spec.id}`);
    }
    seen.add(spec.id);
    seen.add(spec.package);
    seen.add(spec.artifact);
  }
  return parsed.platforms;
}

function ensureBuilt(skipBuild) {
  const entry = join(tsRoot, "dist", "index.js");
  if (skipBuild) {
    if (!existsSync(entry)) {
      throw new Error(
        "dist/index.js is missing. Run npm run build in bindings/typescript, or omit --skip-build.",
      );
    }
    return;
  }
  execFileSync("npm", ["ci"], { cwd: tsRoot, stdio: "inherit" });
  execFileSync("npm", ["run", "build"], { cwd: tsRoot, stdio: "inherit" });
}

function walkFiles(dir) {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walkFiles(path));
    else out.push(path);
  }
  return out;
}

function collectArchives(dir) {
  if (!existsSync(dir)) throw new Error(`FFI archive directory does not exist: ${dir}`);
  return walkFiles(dir).filter((path) => path.endsWith(".tar.gz"));
}

function archiveFor(spec, archives) {
  const suffix = `-${spec.artifact}.tar.gz`;
  const matches = archives.filter((path) => path.endsWith(suffix));
  if (matches.length !== 1) {
    throw new Error(
      `expected one FFI archive ending with ${suffix} for ${spec.id}, found ${matches.length}`,
    );
  }
  return matches[0];
}

function extractLib(archive, spec, destDir) {
  rmSync(destDir, { recursive: true, force: true });
  mkdirSync(destDir, { recursive: true });
  execFileSync("tar", ["-xzf", archive, "-C", destDir]);
  const found = walkFiles(destDir).filter((path) => basename(path) === spec.lib);
  if (found.length !== 1) {
    throw new Error(`${archive} should contain exactly one ${spec.lib}, found ${found.length}`);
  }
  return found[0];
}

function localLibrary(spec) {
  const candidates = [
    join(repoRoot, "target", "release", spec.lib),
    join(repoRoot, "target", "debug", spec.lib),
  ];
  for (const path of candidates) {
    if (existsSync(path)) return path;
  }
  throw new Error(
    `no local ${spec.lib} for ${spec.id}. Run \`cargo build --release -p ontographia-ffi\`.\nLooked in:\n  ${candidates.join("\n  ")}`,
  );
}

function platformReadme(spec) {
  const libc = spec.libc ? ` (${spec.libc})` : "";
  return `# ${spec.package}

Prebuilt \`libontographia_ffi\` for \`${spec.id}\`${libc}.

Optional dependency of \`@edgesentry/ontographia\`. npm installs this package on a matching host. Install the main package, not this one.

Shared library: \`./${spec.lib}\`.
`;
}

function stagePlatform(spec, libPath, version, stageRoot) {
  const dir = join(stageRoot, spec.id);
  mkdirSync(dir, { recursive: true });
  const pkg = {
    name: spec.package,
    version,
    description: `Prebuilt libontographia_ffi for ${spec.id}. Optional dependency of @edgesentry/ontographia.`,
    license: "Apache-2.0",
    repository: {
      type: "git",
      url: "git+https://github.com/edgesentry/ontographia.git",
      directory: "bindings/typescript",
    },
    publishConfig: { access: "public" },
    // Install filters for the optional dependency. They do not gate npm publish:
    // the Linux Release runner publishes darwin and win32 the same way.
    // ENEEDAUTH on one name is that package's Trusted Publisher. See docs/release.md.
    os: [spec.os],
    cpu: [spec.cpu],
    main: `./${spec.lib}`,
    files: [spec.lib, "README.md", "LICENSE"],
    engines: { node: ">=22" },
  };
  if (spec.libc) pkg.libc = [spec.libc];
  writeFileSync(join(dir, "package.json"), `${JSON.stringify(pkg, null, 2)}\n`);
  writeFileSync(join(dir, "README.md"), platformReadme(spec));
  cpSync(join(repoRoot, "LICENSE"), join(dir, "LICENSE"));
  cpSync(libPath, join(dir, spec.lib));
  return dir;
}

function stageMain(version, platforms, stageRoot) {
  const dir = join(stageRoot, "ontographia");
  mkdirSync(join(dir, "npm"), { recursive: true });
  const pkg = JSON.parse(readFileSync(join(tsRoot, "package.json"), "utf8"));
  if (pkg.scripts) delete pkg.scripts.prepublishOnly;
  pkg.version = version;
  pkg.optionalDependencies = Object.fromEntries(
    platforms.map((spec) => [spec.package, version]),
  );
  writeFileSync(join(dir, "package.json"), `${JSON.stringify(pkg, null, 2)}\n`);
  cpSync(join(tsRoot, "README.md"), join(dir, "README.md"));
  cpSync(join(repoRoot, "LICENSE"), join(dir, "LICENSE"));
  cpSync(join(tsRoot, "dist"), join(dir, "dist"), { recursive: true });
  cpSync(join(tsRoot, "npm", "platforms.json"), join(dir, "npm", "platforms.json"));
  return dir;
}

function npmPack(dir, destination) {
  const stdout = execFileSync(
    "npm",
    ["pack", "--json", "--pack-destination", destination],
    { cwd: dir, encoding: "utf8" },
  );
  const parsed = JSON.parse(stdout);
  if (!Array.isArray(parsed) || typeof parsed[0]?.filename !== "string") {
    throw new Error(`unexpected npm pack output: ${stdout}`);
  }
  return join(destination, parsed[0].filename);
}

function readPackedJson(tgz) {
  const stdout = execFileSync("tar", ["-xOzf", tgz, "package/package.json"], {
    encoding: "utf8",
  });
  return JSON.parse(stdout);
}

function listPacked(tgz) {
  return execFileSync("tar", ["-tzf", tgz], { encoding: "utf8" })
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

function assertPacked(mainTgz, platformTgz, version, platforms, requireAllPlatforms) {
  const main = readPackedJson(mainTgz);
  if (main.name !== "@edgesentry/ontographia") {
    throw new Error(`main tarball name is ${main.name}`);
  }
  if (main.version !== version) {
    throw new Error(`main tarball version ${main.version} != ${version}`);
  }
  if (main.scripts?.prepublishOnly) {
    throw new Error("published manifest still has prepublishOnly");
  }
  const deps = main.optionalDependencies ?? {};
  for (const spec of platforms) {
    if (deps[spec.package] !== version) {
      throw new Error(`optionalDependencies[${spec.package}] is ${deps[spec.package]}, want ${version}`);
    }
  }
  if (Object.keys(deps).length !== platforms.length) {
    throw new Error(
      `optionalDependencies has ${Object.keys(deps).length} entries, catalog has ${platforms.length}`,
    );
  }
  const mainFiles = listPacked(mainTgz);
  for (const required of [
    "package/dist/index.js",
    "package/dist/index.d.ts",
    "package/npm/platforms.json",
    "package/README.md",
  ]) {
    if (!mainFiles.includes(required)) {
      throw new Error(`main tarball is missing ${required}`);
    }
  }
  if (mainFiles.some((name) => name.endsWith("libontographia_ffi.so") || name.endsWith(".dll") || name.endsWith(".dylib"))) {
    throw new Error("main tarball must not vendor native libraries; those live in platform packages");
  }

  if (requireAllPlatforms && platformTgz.size !== platforms.length) {
    throw new Error(`packed ${platformTgz.size} platform tarballs, catalog has ${platforms.length}`);
  }
  if (platformTgz.size === 0) throw new Error("no platform tarball was packed");

  for (const spec of platforms) {
    const tgz = platformTgz.get(spec.package);
    if (!tgz) continue;
    const pkg = readPackedJson(tgz);
    if (pkg.name !== spec.package || pkg.version !== version) {
      throw new Error(`platform tarball ${spec.package}@${pkg.version} does not match ${version}`);
    }
    if (pkg.os?.[0] !== spec.os || pkg.cpu?.[0] !== spec.cpu) {
      throw new Error(`${spec.package} os/cpu is ${pkg.os}/${pkg.cpu}, catalog says ${spec.os}/${spec.cpu}`);
    }
    if (spec.libc) {
      if (pkg.libc?.[0] !== spec.libc) {
        throw new Error(`${spec.package} libc is ${pkg.libc}, catalog says ${spec.libc}`);
      }
    } else if (pkg.libc) {
      throw new Error(`${spec.package} should not set libc`);
    }
    const names = listPacked(tgz);
    if (!names.includes(`package/${spec.lib}`)) {
      throw new Error(`${tgz} is missing package/${spec.lib}`);
    }
  }
}

function resolveOut(dir) {
  const resolved = resolve(dir);
  if (resolved === repoRoot || resolved === tsRoot || repoRoot.startsWith(`${resolved}/`)) {
    throw new Error(`refusing to wipe ${resolved}`);
  }
  return resolved;
}

function run() {
  const args = parseArgs(process.argv.slice(2));
  const version = workspaceVersion();
  const source = JSON.parse(readFileSync(join(tsRoot, "package.json"), "utf8"));
  if (source.version !== version) {
    throw new Error(
      `bindings/typescript/package.json version ${source.version} != Cargo.toml ${version}. Run scripts/bump-version.sh ${version}.`,
    );
  }
  const platforms = readCatalog();
  ensureBuilt(args.skipBuild);

  const specs = [];
  if (args.mode === "local") {
    const id = `${platform()}-${arch()}`;
    const spec = platforms.find((item) => item.id === id);
    if (!spec) {
      throw new Error(`no prebuild catalog entry for ${id}. Use --ffi-archives on a Release host.`);
    }
    specs.push({ spec, libPath: localLibrary(spec) });
  } else {
    const archives = collectArchives(resolve(args.ffiArchives));
    const extractRoot = join(tmpdir(), `ontographia-ffi-extract-${process.pid}`);
    for (const spec of platforms) {
      const archive = archiveFor(spec, archives);
      const libPath = extractLib(archive, spec, join(extractRoot, spec.id));
      specs.push({ spec, libPath });
    }
  }

  const outDir = resolveOut(args.outDir);
  rmSync(outDir, { recursive: true, force: true });
  mkdirSync(outDir, { recursive: true });
  const stageRoot = join(tmpdir(), `ontographia-npm-stage-${process.pid}`);
  rmSync(stageRoot, { recursive: true, force: true });
  mkdirSync(stageRoot, { recursive: true });

  const platformTgz = new Map();
  for (const { spec, libPath } of specs) {
    const dir = stagePlatform(spec, libPath, version, stageRoot);
    const tgz = npmPack(dir, outDir);
    platformTgz.set(spec.package, tgz);
    console.log(`packed ${tgz}`);
  }
  const mainDir = stageMain(version, platforms, stageRoot);
  const mainTgz = npmPack(mainDir, outDir);
  console.log(`packed ${mainTgz}`);

  assertPacked(mainTgz, platformTgz, version, platforms, args.mode === "archives");
  console.log(`npm pack ok (${version}, ${args.mode})`);
}

try {
  run();
} catch (err) {
  console.error(err instanceof Error ? err.message : String(err));
  process.exit(1);
}
