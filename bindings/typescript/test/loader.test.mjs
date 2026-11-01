import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { arch, platform } from "node:os";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import { ffiLibraryCandidates } from "../dist/ffi.js";

const here = dirname(fileURLToPath(import.meta.url));
const pkgRoot = join(here, "..");
const repoRoot = join(pkgRoot, "..", "..");
const catalog = JSON.parse(
  readFileSync(join(pkgRoot, "npm", "platforms.json"), "utf8"),
);

describe("ffi loader", { concurrency: false }, () => {
  it("catalog lists the four Release platforms", () => {
    const ids = catalog.platforms.map((item) => item.id).sort();
    assert.deepEqual(ids, [
      "darwin-arm64",
      "linux-arm64",
      "linux-x64",
      "win32-x64",
    ]);
    for (const spec of catalog.platforms) {
      assert.equal(spec.package, `@edgesentry/ontographia-${spec.id}`);
      if (spec.os === "linux") assert.equal(spec.libc, "glibc");
      else assert.equal(spec.libc, undefined);
    }
  });

  it("searches ONTOGRAPHIA_FFI_DIR, then the npm prebuild, then target/", () => {
    const spec = catalog.platforms.find(
      (item) => item.id === `${platform()}-${arch()}`,
    );
    assert.ok(spec, `catalog entry for ${platform()}-${arch()}`);
    const previous = process.env.ONTOGRAPHIA_FFI_DIR;
    process.env.ONTOGRAPHIA_FFI_DIR = "/custom/ontographia-ffi";
    try {
      const paths = ffiLibraryCandidates();
      const bundled = join(pkgRoot, "node_modules", spec.package, spec.lib);
      const release = join(repoRoot, "target", "release", spec.lib);
      const debug = join(repoRoot, "target", "debug", spec.lib);
      assert.equal(paths[0], join("/custom/ontographia-ffi", spec.lib));
      assert.ok(paths.indexOf(bundled) > 0, paths.join("\n"));
      assert.ok(paths.indexOf(release) > paths.indexOf(bundled), paths.join("\n"));
      assert.ok(paths.indexOf(debug) > paths.indexOf(release), paths.join("\n"));
    } finally {
      if (previous === undefined) delete process.env.ONTOGRAPHIA_FFI_DIR;
      else process.env.ONTOGRAPHIA_FFI_DIR = previous;
    }
  });

  it("ONTOGRAPHIA_FFI_LIB overrides the prebuild and the checkout library", () => {
    const ontology = join(repoRoot, "examples", "manufacturing.native.yaml");
    const result = spawnSync(
      process.execPath,
      [
        "--input-type=module",
        "-e",
        `
        import { buildCypherFromFiles } from "./dist/index.js";
        try {
          buildCypherFromFiles(${JSON.stringify(ontology)}, "{}");
        } catch (err) {
          console.error(err instanceof Error ? err.message : String(err));
          process.exit(1);
        }
        `,
      ],
      {
        cwd: pkgRoot,
        env: {
          ...process.env,
          ONTOGRAPHIA_FFI_LIB: "/no/such/libontographia_ffi.so",
        },
        encoding: "utf8",
      },
    );
    assert.notEqual(result.status, 0, result.stdout);
    assert.match(
      `${result.stderr}\n${result.stdout}`,
      /ONTOGRAPHIA_FFI_LIB does not exist/,
    );
  });
});
