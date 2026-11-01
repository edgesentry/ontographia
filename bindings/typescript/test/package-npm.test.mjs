import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { chmodSync, mkdtempSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const pkgRoot = join(here, "..");
const repoRoot = join(pkgRoot, "..", "..");
const catalog = JSON.parse(
  readFileSync(join(pkgRoot, "npm", "platforms.json"), "utf8"),
);

function readPackedJson(tgz) {
  const stdout = execFileSync("tar", ["-xOzf", tgz, "package/package.json"], {
    encoding: "utf8",
  });
  return JSON.parse(stdout);
}

describe("npm pack", () => {
  it("refuses publish-npm.sh outside the Release workflow without calling npm", () => {
    const work = mkdtempSync(join(tmpdir(), "ontographia-no-publish-"));
    const bin = join(work, "bin");
    const log = join(work, "npm.log");
    mkdirSync(bin);
    writeFileSync(
      join(bin, "npm"),
      `#!/bin/sh\necho "$@" >> ${JSON.stringify(log)}\nexit 99\n`,
    );
    chmodSync(join(bin, "npm"), 0o755);
    mkdirSync(join(work, "tarballs"));
    writeFileSync(log, "");
    const env = { ...process.env, PATH: `${bin}:${process.env.PATH ?? ""}` };
    delete env.GITHUB_ACTIONS;
    delete env.GITHUB_WORKFLOW;
    delete env.GITHUB_JOB;
    env.NODE_AUTH_TOKEN = "must-not-be-sent";
    const result = spawnSync(
      "bash",
      [join(repoRoot, "scripts", "publish-npm.sh"), join(work, "tarballs")],
      { encoding: "utf8", env },
    );
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /forbidden outside the GitHub Actions Release/);
    assert.equal(readFileSync(log, "utf8").length, 0);
    rmSync(work, { recursive: true, force: true });
  });

  it("refuses npm publish of the source package", () => {
    const result = spawnSync(
      process.execPath,
      [join(repoRoot, "scripts", "refuse-npm-publish.mjs")],
      { encoding: "utf8" },
    );
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /package-npm\.mjs/);
    const pkg = JSON.parse(readFileSync(join(pkgRoot, "package.json"), "utf8"));
    assert.match(pkg.scripts.prepublishOnly, /refuse-npm-publish\.mjs/);
  });

  it("stamps optionalDependencies and packs each platform archive", () => {
    const work = mkdtempSync(join(tmpdir(), "ontographia-npm-"));
    try {
      const archives = join(work, "archives");
      const stage = join(work, "stage");
      mkdirSync(archives);
      for (const spec of catalog.platforms) {
        const folderName = `libontographia_ffi-0.0.0-${spec.artifact}`;
        const folder = join(stage, folderName);
        mkdirSync(folder, { recursive: true });
        writeFileSync(join(folder, spec.lib), `fake ${spec.id}\n`);
        execFileSync("tar", ["-czf", join(archives, `${folderName}.tar.gz`), "-C", stage, folderName]);
      }
      const out = join(work, "out");
      const result = spawnSync(
        process.execPath,
        [
          join(repoRoot, "scripts", "package-npm.mjs"),
          "--ffi-archives",
          archives,
          "--skip-build",
          "--out",
          out,
        ],
        { cwd: repoRoot, encoding: "utf8" },
      );
      assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
      const cargo = execFileSync("bash", [join(repoRoot, "scripts", "workspace-version.sh")], {
        encoding: "utf8",
      }).trim();
      const tarballs = readdirSync(out)
        .filter((name) => name.endsWith(".tgz"))
        .map((name) => join(out, name));
      assert.equal(tarballs.length, catalog.platforms.length + 1);

      const mainTgz = tarballs.find((path) =>
        path.endsWith(`edgesentry-ontographia-${cargo}.tgz`),
      );
      assert.ok(mainTgz, tarballs.join("\n"));
      const main = readPackedJson(mainTgz);
      assert.equal(main.version, cargo);
      assert.equal(main.scripts?.prepublishOnly, undefined);
      for (const spec of catalog.platforms) {
        assert.equal(main.optionalDependencies[spec.package], cargo);
        const platformTgz = tarballs.find((path) =>
          path.endsWith(`edgesentry-ontographia-${spec.id}-${cargo}.tgz`),
        );
        assert.ok(platformTgz, tarballs.join("\n"));
        const packed = readPackedJson(platformTgz);
        assert.equal(packed.os[0], spec.os);
        assert.equal(packed.cpu[0], spec.cpu);
        assert.equal(packed.main, `./${spec.lib}`);
        if (spec.libc) assert.deepEqual(packed.libc, [spec.libc]);
        else assert.equal(packed.libc, undefined);
        const names = execFileSync("tar", ["-tzf", platformTgz], { encoding: "utf8" });
        assert.match(names, new RegExp(`package/${spec.lib}`));
      }
    } finally {
      rmSync(work, { recursive: true, force: true });
    }
  });
});
