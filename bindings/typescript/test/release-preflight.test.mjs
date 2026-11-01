import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import {
  credentialProblem,
  evaluatePublishers,
  extractPublishers,
  FIX_STEPS,
  PACKAGES,
  readsTrustedPublishers,
} from "../../../scripts/check-npm-trusted-publishers.mjs";
import { workflowProblems } from "../../../scripts/check-release-workflow.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..", "..");
const releaseYml = join(repoRoot, ".github", "workflows", "release.yml");
const SECRET = "npm_test_secret_value";

function childEnv(extra = {}) {
  const env = { ...process.env };
  for (const key of [
    "NPM_TOKEN",
    "NPM_TRUST_TOKEN",
    "NPM_TRUST_OTP",
    "NODE_AUTH_TOKEN",
    "ONTOGRAPHIA_NPM_REGISTRY",
    "FAKE_CURL_MODE",
    "CURL_BIN",
    "GITHUB_ACTIONS",
  ]) {
    delete env[key];
  }
  return { ...env, ...extra };
}

function runNode(script, args, env) {
  return spawnSync(process.execPath, [script, ...args], {
    cwd: repoRoot,
    encoding: "utf8",
    env,
  });
}

// spawnSync blocks the event loop, so a mock HTTP server in this process cannot answer.
function runNodeAsync(script, args, env) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(process.execPath, [script, ...args], { cwd: repoRoot, env });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.on("error", reject);
    child.on("close", (status) => resolvePromise({ status, stdout, stderr }));
  });
}

function goodConfig(overrides = {}) {
  return {
    id: "abc",
    type: "github",
    claims: {
      repository: "edgesentry/ontographia",
      workflow_ref: { file: "release.yml" },
    },
    permissions: ["createPackage", "createStagedPackage"],
    ...overrides,
  };
}

function listen(handler) {
  return new Promise((resolve, reject) => {
    const server = createServer((req, res) => {
      try {
        const url = new URL(req.url ?? "/", "http://127.0.0.1");
        const result = handler({
          pathname: url.pathname,
          authorization: req.headers.authorization || "",
          otp: req.headers["npm-otp"] || "",
        });
        res.writeHead(result.status, { "content-type": "application/json" });
        res.end(JSON.stringify(result.body ?? {}));
      } catch (err) {
        res.writeHead(500, { "content-type": "application/json" });
        res.end(JSON.stringify({ message: err instanceof Error ? err.message : String(err) }));
      }
    });
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        reject(new Error("test registry did not bind"));
        return;
      }
      resolve({ server, base: `http://127.0.0.1:${address.port}` });
    });
    server.on("error", reject);
  });
}

function packageName(pathname) {
  if (pathname.startsWith("/-/package/") && pathname.endsWith("/trust")) {
    return decodeURIComponent(pathname.slice("/-/package/".length, -"/trust".length));
  }
  return decodeURIComponent(pathname.replace(/^\//, ""));
}

describe("release workflow self-check", () => {
  it("accepts .github/workflows/release.yml", () => {
    const text = readFileSync(releaseYml, "utf8");
    assert.deepEqual(workflowProblems(text), []);
    const result = runNode(
      join(repoRoot, "scripts", "check-release-workflow.mjs"),
      [],
      childEnv(),
    );
    assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
    assert.match(result.stdout, /release workflow ok: \.github\/workflows\/release\.yml name=Release job=publish-npm/);
  });

  it("rejects a missing checkout, GH_REPO, renamed publish job, or workflow name", () => {
    const text = readFileSync(releaseYml, "utf8");
    const noRepo = text.replace(/^\s*GH_REPO\s*:.*$/m, "");
    assert.match(workflowProblems(noRepo).join("\n"), /GH_REPO/);

    // Other jobs also check out. Strip every checkout so upload-assets fails the check.
    const noCheckouts = text.replace(
      /^[ \t]*-\s*uses:\s*actions\/checkout@.*$/gm,
      "      - name: skip checkout",
    );
    assert.match(workflowProblems(noCheckouts).join("\n"), /upload-assets must check out/);

    const renamed = text.replace("\n  publish-npm:\n", "\n  publish-packages:\n");
    assert.match(workflowProblems(renamed).join("\n"), /job id publish-npm is missing/);

    const renamedWorkflow = text.replace(/^name: Release$/m, "name: Release check");
    assert.match(workflowProblems(renamedWorkflow).join("\n"), /workflow name is Release check/);

    const work = mkdtempSync(join(tmpdir(), "ontographia-workflow-"));
    const copy = join(work, "broken.yml");
    writeFileSync(copy, noRepo);
    const result = runNode(
      join(repoRoot, "scripts", "check-release-workflow.mjs"),
      ["--file", copy],
      childEnv(),
    );
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /GH_REPO/);
    rmSync(work, { recursive: true, force: true });
  });

  it("does not pass NPM_TRUST_TOKEN or NPM_TOKEN into preflight or publish-npm", () => {
    for (const rel of [
      ".github/workflows/release-check.yml",
      ".github/workflows/preflight-release.yml",
      ".github/workflows/release.yml",
    ]) {
      const text = readFileSync(join(repoRoot, rel), "utf8");
      assert.equal(text.includes("NPM_TRUST_TOKEN"), false, rel);
      assert.equal(text.includes("secrets.NPM_TOKEN"), false, rel);
    }
    const release = readFileSync(releaseYml, "utf8");
    const publish = release.split("\n  publish-npm:\n")[1] ?? "";
    assert.match(publish, /id-token:\s*write/);
    assert.equal(/^\s*NPM_TOKEN\s*:/m.test(publish), false);
  });
});

describe("npm trusted publisher records", () => {
  it("matches the registry shape and the flattened npm trust list shape", () => {
    assert.equal(evaluatePublishers([goodConfig()]).ok, true);
    assert.equal(
      evaluatePublishers([
        {
          type: "github",
          repository: "edgesentry/ontographia",
          file: "release.yml",
          permissions: ["createPackage"],
        },
      ]).ok,
      true,
    );
    const wrapped = extractPublishers({ objects: [goodConfig()] });
    assert.equal(wrapped.length, 1);
    assert.equal(evaluatePublishers(wrapped).ok, true);
    assert.match(evaluatePublishers([]).detail, /no trusted publisher/);
    assert.match(
      evaluatePublishers([
        goodConfig({
          permissions: ["createStagedPackage"],
          claims: {
            repository: "edgesentry/ontographia",
            workflow_ref: { file: "release.yml" },
          },
        }),
      ]).detail,
      /createPackage/,
    );
    assert.match(
      evaluatePublishers([
        {
          type: "github",
          claims: {
            repository: "edgesentry/ontographia",
            workflow_ref: { file: "publish.yml" },
          },
          permissions: ["createPackage"],
        },
      ]).detail,
      /release\.yml/,
    );
    assert.match(
      evaluatePublishers([
        {
          type: "github",
          claims: {
            repository: "elsewhere/ontographia",
            workflow_ref: { file: "release.yml" },
          },
          permissions: ["createPackage"],
        },
      ]).detail,
      /edgesentry\/ontographia/,
    );
    assert.match(
      evaluatePublishers([
        {
          type: "github",
          claims: {
            repository: "edgesentry/ontographia",
            workflow_ref: { file: "release.yml" },
            environment: "production",
          },
          permissions: ["createPackage"],
        },
      ]).detail,
      /environment/,
    );
    assert.match(FIX_STEPS, /npm trust list/);
    assert.match(FIX_STEPS, /CI does not call/);
    assert.match(FIX_STEPS, /Do not store a granular token/);
    assert.match(FIX_STEPS, /NPM_TOKEN in GitHub Actions/);
    assert.match(FIX_STEPS, /outside GitHub Actions/);
    assert.equal(FIX_STEPS.includes("repository secret"), false);
    assert.equal(readsTrustedPublishers({}), false);
    assert.equal(readsTrustedPublishers({ NPM_TRUST_TOKEN: "  " }), false);
    assert.equal(readsTrustedPublishers({ NPM_TRUST_TOKEN: "trust-token" }), true);
    assert.equal(
      readsTrustedPublishers({ GITHUB_ACTIONS: "true", NPM_TRUST_TOKEN: "trust-token" }),
      false,
    );
    assert.equal(PACKAGES.length, 5);
    for (const name of PACKAGES) assert.match(FIX_STEPS, new RegExp(name.replace("/", "\\/")));
  });

  it("refuses NPM_TOKEN before it talks to the registry", () => {
    assert.match(credentialProblem({ NPM_TOKEN: SECRET }), /NPM_TOKEN is set/);
    assert.equal(
      credentialProblem({ NODE_AUTH_TOKEN: "XXXXX-XXXXX-XXXXX-XXXXX" }),
      "",
    );
    assert.match(credentialProblem({ NODE_AUTH_TOKEN: SECRET }), /NODE_AUTH_TOKEN is set/);
    const result = runNode(
      join(repoRoot, "scripts", "check-npm-trusted-publishers.mjs"),
      [],
      childEnv({
        NPM_TOKEN: SECRET,
        ONTOGRAPHIA_NPM_REGISTRY: "http://127.0.0.1:9",
      }),
    );
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /NPM_TOKEN is set/);
    assert.equal(result.stderr.includes(SECRET), false);
    assert.equal(result.stdout.includes(SECRET), false);
    assert.equal(result.stderr.includes("ECONNREFUSED") || result.stderr.includes("127.0.0.1:9"), false);
  });

  it("skips the trust API and warns when no token is set", async () => {
    let trustHits = 0;
    const registry = await listen(({ pathname }) => {
      if (pathname.includes("/trust")) {
        trustHits += 1;
        return { status: 401, body: { message: "Bearer token authorization is required" } };
      }
      return { status: 200, body: { name: packageName(pathname), "dist-tags": { latest: "0.0.0" } } };
    });
    try {
      const result = await runNodeAsync(
        join(repoRoot, "scripts", "check-npm-trusted-publishers.mjs"),
        [],
        childEnv({ ONTOGRAPHIA_NPM_REGISTRY: registry.base }),
      );
      assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
      assert.match(result.stdout, /@edgesentry\/ontographia is on the registry \(latest 0\.0\.0\)/);
      assert.match(result.stdout, /npm packages on registry; trusted publisher settings were not read/);
      assert.match(result.stderr, /npm trust list @edgesentry\/ontographia --json/);
      assert.match(result.stderr, /npm trust list @edgesentry\/ontographia-win32-x64 --json/);
      assert.match(result.stderr, /release\.yml/);
      assert.match(result.stderr, /createPackage/);
      assert.equal(result.stdout.includes("npm trusted publishers ok"), false);
      assert.equal(result.stderr.includes("npm publish ok"), false);
      assert.equal(trustHits, 0);
    } finally {
      registry.server.close();
    }
  });

  it("ignores NPM_TRUST_TOKEN in GitHub Actions", async () => {
    let trustHits = 0;
    const registry = await listen(({ pathname, authorization }) => {
      if (pathname.includes("/trust")) {
        trustHits += 1;
        assert.equal(authorization, "");
        return { status: 401, body: { message: "Bearer token authorization is required" } };
      }
      return { status: 200, body: { name: packageName(pathname), "dist-tags": { latest: "0.1.7" } } };
    });
    try {
      const result = await runNodeAsync(
        join(repoRoot, "scripts", "check-npm-trusted-publishers.mjs"),
        [],
        childEnv({
          ONTOGRAPHIA_NPM_REGISTRY: registry.base,
          GITHUB_ACTIONS: "true",
          NPM_TRUST_TOKEN: "trust-token",
          NPM_TRUST_OTP: "123456",
        }),
      );
      assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
      assert.match(result.stdout, /trusted publisher settings were not read/);
      assert.match(result.stderr, /NPM_TRUST_TOKEN is set and ignored in GitHub Actions/);
      assert.equal(result.stdout.includes("trust-token"), false);
      assert.equal(result.stderr.includes("trust-token"), false);
      assert.equal(result.stderr.includes("123456"), false);
      assert.equal(trustHits, 0);
    } finally {
      registry.server.close();
    }
  });

  it("still fails when a package is missing from the registry", async () => {
    const registry = await listen(({ pathname }) => {
      const name = packageName(pathname);
      if (name === "@edgesentry/ontographia-win32-x64") {
        return { status: 404, body: { message: "not found" } };
      }
      return { status: 200, body: { name, "dist-tags": { latest: "0.0.0" } } };
    });
    try {
      const result = await runNodeAsync(
        join(repoRoot, "scripts", "check-npm-trusted-publishers.mjs"),
        [],
        childEnv({ ONTOGRAPHIA_NPM_REGISTRY: registry.base, GITHUB_ACTIONS: "true" }),
      );
      assert.notEqual(result.status, 0);
      assert.match(result.stderr, /npm package presence check failed/);
      assert.match(result.stderr, /@edgesentry\/ontographia-win32-x64: package is not on the registry/);
      assert.equal(result.stdout.includes("trusted publisher settings were not read"), false);
    } finally {
      registry.server.close();
    }
  });

  it("fails a local token read on 401 and on an npm-otp challenge", async () => {
    const unauthorized = await listen(({ pathname, authorization }) => {
      if (pathname.includes("/trust")) {
        if (authorization && authorization !== "Bearer trust-token") {
          return { status: 500, body: { message: "unexpected authorization" } };
        }
        return { status: 401, body: { message: "Bearer token authorization is required" } };
      }
      return { status: 200, body: { name: packageName(pathname), "dist-tags": { latest: "0.0.0" } } };
    });
    try {
      const result = await runNodeAsync(
        join(repoRoot, "scripts", "check-npm-trusted-publishers.mjs"),
        [],
        childEnv({
          ONTOGRAPHIA_NPM_REGISTRY: unauthorized.base,
          NPM_TRUST_TOKEN: "trust-token",
        }),
      );
      assert.notEqual(result.status, 0);
      assert.match(result.stderr, /HTTP 401/);
      assert.match(result.stderr, /npm trust list/);
      assert.equal(result.stderr.includes("trust-token"), false);
    } finally {
      unauthorized.server.close();
    }

    const otp = await listen(({ pathname, authorization, otp: code }) => {
      if (pathname.includes("/trust")) {
        if (!authorization) {
          return { status: 401, body: { message: "Bearer token authorization is required" } };
        }
        assert.equal(authorization, "Bearer trust-token");
        assert.equal(code, "");
        return { status: 401, body: { message: "npm-otp required" } };
      }
      return { status: 200, body: { name: packageName(pathname), "dist-tags": { latest: "0.0.0" } } };
    });
    try {
      const result = await runNodeAsync(
        join(repoRoot, "scripts", "check-npm-trusted-publishers.mjs"),
        [],
        childEnv({
          ONTOGRAPHIA_NPM_REGISTRY: otp.base,
          NPM_TRUST_TOKEN: "trust-token",
        }),
      );
      assert.notEqual(result.status, 0);
      assert.match(result.stderr, /npm-otp/);
      assert.match(result.stderr, /npm trust list locally/);
    } finally {
      otp.server.close();
    }
  });

  it("accepts a token when every package allows publish from release.yml", async () => {
    let authed = 0;
    const registry = await listen(({ pathname, authorization }) => {
      if (pathname.includes("/trust")) {
        if (authorization !== "Bearer trust-token") {
          return { status: 401, body: { message: "Bearer token authorization is required" } };
        }
        authed += 1;
        return { status: 200, body: [goodConfig()] };
      }
      return {
        status: 200,
        body: { name: packageName(pathname), "dist-tags": { latest: "0.1.7" } },
      };
    });
    try {
      const result = await runNodeAsync(
        join(repoRoot, "scripts", "check-npm-trusted-publishers.mjs"),
        [],
        childEnv({
          ONTOGRAPHIA_NPM_REGISTRY: registry.base,
          NPM_TRUST_TOKEN: "trust-token",
        }),
      );
      assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
      assert.match(result.stdout, /npm trusted publishers ok/);
      assert.equal(authed, PACKAGES.length);
      for (const name of PACKAGES) {
        assert.match(result.stdout, new RegExp(`trusted publisher ok: ${name.replace("/", "\\/")}`));
      }
    } finally {
      registry.server.close();
    }
  });

  it("names the package whose publisher does not allow npm publish", async () => {
    const registry = await listen(({ pathname, authorization }) => {
      const name = packageName(pathname);
      if (pathname.includes("/trust")) {
        if (authorization !== "Bearer trust-token") {
          return { status: 401, body: { message: "Bearer token authorization is required" } };
        }
        const permissions =
          name === "@edgesentry/ontographia-win32-x64"
            ? ["createStagedPackage"]
            : ["createPackage"];
        return {
          status: 200,
          body: [
            {
              type: "github",
              claims: {
                repository: "edgesentry/ontographia",
                workflow_ref: { file: "release.yml" },
              },
              permissions,
            },
          ],
        };
      }
      return { status: 200, body: { name, "dist-tags": { latest: "0.0.0" } } };
    });
    try {
      const result = await runNodeAsync(
        join(repoRoot, "scripts", "check-npm-trusted-publishers.mjs"),
        [],
        childEnv({
          ONTOGRAPHIA_NPM_REGISTRY: registry.base,
          NPM_TRUST_TOKEN: "trust-token",
        }),
      );
      assert.notEqual(result.status, 0);
      assert.match(result.stderr, /@edgesentry\/ontographia-win32-x64: permissions are createStagedPackage/);
      assert.match(result.stderr, /Allow npm publish is off/);
      assert.match(result.stdout, /trusted publisher ok: @edgesentry\/ontographia /);
    } finally {
      registry.server.close();
    }
  });
});

describe("registry reachability", () => {
  function writeCurl(dir) {
    const path = join(dir, "curl");
    writeFileSync(
      path,
      `#!/bin/sh
body=""
url=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o) body="$2"; shift 2 ;;
    -w|-A|--max-time|--retry|--retry-delay) shift 2 ;;
    -sS|-s|-S) shift ;;
    http://*|https://*) url="$1"; shift ;;
    *) shift ;;
  esac
done
printf 'ok' > "$body"
mode="\${FAKE_CURL_MODE:-ok}"
case "$mode" in
  down) exit 28 ;;
  crates403)
    case "$url" in
      *crates.io*) printf '403' ;;
      *) printf '200' ;;
    esac
    ;;
  npm404)
    case "$url" in
      *registry.npmjs.org*) printf '404' ;;
      *) printf '200' ;;
    esac
    ;;
  server500) printf '500' ;;
  *) printf '200' ;;
esac
`,
    );
    chmodSync(path, 0o755);
    return path;
  }

  it("accepts HTTP 200 and 404 and rejects a refused host or HTTP 403", () => {
    const work = mkdtempSync(join(tmpdir(), "ontographia-curl-"));
    try {
      const curl = writeCurl(work);
      const script = join(repoRoot, "scripts", "check-registry-reachability.sh");
      const ok = spawnSync("bash", [script], {
        encoding: "utf8",
        env: childEnv({ CURL_BIN: curl, FAKE_CURL_MODE: "ok" }),
      });
      assert.equal(ok.status, 0, `${ok.stdout}\n${ok.stderr}`);
      assert.match(ok.stdout, /registry reachability ok/);

      const missing = spawnSync("bash", [script], {
        encoding: "utf8",
        env: childEnv({ CURL_BIN: curl, FAKE_CURL_MODE: "npm404" }),
      });
      assert.equal(missing.status, 0, `${missing.stdout}\n${missing.stderr}`);
      assert.match(missing.stdout, /npm reachable \(HTTP 404\)/);

      const forbidden = spawnSync("bash", [script], {
        encoding: "utf8",
        env: childEnv({ CURL_BIN: curl, FAKE_CURL_MODE: "crates403" }),
      });
      assert.notEqual(forbidden.status, 0);
      assert.match(forbidden.stderr, /crates\.io returned HTTP 403/);

      const down = spawnSync("bash", [script], {
        encoding: "utf8",
        env: childEnv({ CURL_BIN: curl, FAKE_CURL_MODE: "down" }),
      });
      assert.notEqual(down.status, 0);
      assert.match(down.stderr, /npm did not respond/);
    } finally {
      rmSync(work, { recursive: true, force: true });
    }
  });
});

describe("npm pack dry-run", () => {
  it("packs stub FFI archives and asserts four platform optionalDependencies", () => {
    const result = runNode(
      join(repoRoot, "scripts", "package-npm-dry-run.mjs"),
      [],
      childEnv(),
    );
    assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
    assert.match(result.stdout, /stub FFI archives/);
    assert.match(result.stdout, /no publish/);
    for (const name of [
      "@edgesentry/ontographia-linux-x64",
      "@edgesentry/ontographia-linux-arm64",
      "@edgesentry/ontographia-darwin-arm64",
      "@edgesentry/ontographia-win32-x64",
    ]) {
      assert.match(result.stdout, new RegExp(`${name.replace("/", "\\/")}@`));
    }
    assert.match(result.stdout, /4 platform optionalDependencies/);
    assert.equal(result.stdout.includes("npm publish "), false);
  });
});
