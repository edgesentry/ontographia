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

function releasePublishEnv(bin) {
  const env = {
    ...process.env,
    PATH: `${bin}:${process.env.PATH ?? ""}`,
    GITHUB_ACTIONS: "true",
    GITHUB_WORKFLOW: "Release",
    GITHUB_JOB: "publish-npm",
    ACTIONS_ID_TOKEN_REQUEST_URL: "https://example.invalid/oidc",
    ACTIONS_ID_TOKEN_REQUEST_TOKEN: "oidc-request",
  };
  delete env.NODE_AUTH_TOKEN;
  delete env.NPM_TOKEN;
  delete env.NPM_CONFIG_USERCONFIG;
  return env;
}

function writePackageTarball(destDir, pkg) {
  const stage = mkdtempSync(join(tmpdir(), "ontographia-tgz-"));
  try {
    const root = join(stage, "package");
    mkdirSync(root);
    writeFileSync(join(root, "package.json"), JSON.stringify(pkg));
    const safe = pkg.name.replace(/^@/, "").replace("/", "-");
    const tgz = join(destDir, `${safe}.tgz`);
    execFileSync("tar", ["-czf", tgz, "-C", stage, "package"]);
    return tgz;
  } finally {
    rmSync(stage, { recursive: true, force: true });
  }
}

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

  it("refuses a real npm token inside the Release job without calling npm", () => {
    const work = mkdtempSync(join(tmpdir(), "ontographia-token-"));
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
    const env = releasePublishEnv(bin);
    env.NODE_AUTH_TOKEN = "npm_real_token";
    const result = spawnSync(
      "bash",
      [join(repoRoot, "scripts", "publish-npm.sh"), join(work, "tarballs")],
      { encoding: "utf8", env },
    );
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /NODE_AUTH_TOKEN is set/);
    assert.equal(readFileSync(log, "utf8").length, 0);
    rmSync(work, { recursive: true, force: true });
  });

  it("publishes with OIDC after dropping the setup-node placeholder token", () => {
    const work = mkdtempSync(join(tmpdir(), "ontographia-oidc-"));
    try {
      const bin = join(work, "bin");
      const log = join(work, "npm.log");
      const tarballs = join(work, "tarballs");
      const npmrc = join(work, ".npmrc");
      mkdirSync(bin);
      mkdirSync(tarballs);
      writeFileSync(
        npmrc,
        "//registry.npmjs.org/:_authToken=${NODE_AUTH_TOKEN}\nregistry=https://registry.npmjs.org/\nalways-auth=true\n",
      );
      writeFileSync(
        join(bin, "npm"),
        `#!/bin/sh
echo "$@" >> ${JSON.stringify(log)}
if [ "$1" = "--version" ]; then
  echo "11.5.1"
  exit 0
fi
if [ "$1" = "view" ]; then
  exit 1
fi
if [ "$1" = "publish" ]; then
  echo "TOKEN=\${NODE_AUTH_TOKEN-unset}" >> ${JSON.stringify(log)}
  exit 0
fi
exit 99
`,
      );
      chmodSync(join(bin, "npm"), 0o755);
      writeFileSync(log, "");
      const version = "9.9.9";
      const platforms = [
        "@edgesentry/ontographia-linux-x64",
        "@edgesentry/ontographia-linux-arm64",
        "@edgesentry/ontographia-darwin-arm64",
        "@edgesentry/ontographia-win32-x64",
      ];
      for (const name of platforms) {
        writePackageTarball(tarballs, { name, version });
      }
      writePackageTarball(tarballs, {
        name: "@edgesentry/ontographia",
        version,
        optionalDependencies: Object.fromEntries(platforms.map((name) => [name, version])),
      });
      const env = releasePublishEnv(bin);
      env.NODE_AUTH_TOKEN = "XXXXX-XXXXX-XXXXX-XXXXX";
      env.NPM_CONFIG_USERCONFIG = npmrc;
      const result = spawnSync(
        "bash",
        [join(repoRoot, "scripts", "publish-npm.sh"), tarballs],
        { encoding: "utf8", env },
      );
      assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
      const trace = readFileSync(log, "utf8");
      assert.match(trace, /--version/);
      const publishes = trace.split("\n").filter((line) => line.startsWith("publish "));
      assert.equal(publishes.length, 5);
      for (const line of publishes) {
        assert.match(line, /^publish \S+\.tgz --access public$/);
        assert.equal(line.includes("--provenance"), false);
      }
      assert.equal(trace.includes("TOKEN=unset\n") ? trace.split("TOKEN=unset").length - 1 : 0, 5);
      assert.equal(readFileSync(npmrc, "utf8").includes("_authToken"), false);
      assert.match(readFileSync(npmrc, "utf8"), /^registry=https:\/\/registry\.npmjs\.org\/$/m);
      assert.match(result.stdout, /Publishing @edgesentry\/ontographia-linux-x64@9\.9\.9/);
      assert.match(result.stdout, /Publishing @edgesentry\/ontographia@9\.9\.9/);
    } finally {
      rmSync(work, { recursive: true, force: true });
    }
  });

  it("refuses npm older than Trusted Publishing support", () => {
    const work = mkdtempSync(join(tmpdir(), "ontographia-old-npm-"));
    const bin = join(work, "bin");
    const log = join(work, "npm.log");
    mkdirSync(bin);
    writeFileSync(
      join(bin, "npm"),
      `#!/bin/sh
echo "$@" >> ${JSON.stringify(log)}
if [ "$1" = "--version" ]; then
  echo "10.9.2"
  exit 0
fi
exit 99
`,
    );
    chmodSync(join(bin, "npm"), 0o755);
    mkdirSync(join(work, "tarballs"));
    writeFileSync(log, "");
    const result = spawnSync(
      "bash",
      [join(repoRoot, "scripts", "publish-npm.sh"), join(work, "tarballs")],
      { encoding: "utf8", env: releasePublishEnv(bin) },
    );
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /npm 10\.9\.2 cannot use Trusted Publishing/);
    assert.equal(readFileSync(log, "utf8").includes("publish "), false);
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
