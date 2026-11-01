#!/usr/bin/env node
// Confirm the five Release packages are on the npm registry.
// Does not publish. Does not read NPM_TOKEN.
//
// GitHub Actions (GITHUB_ACTIONS=true) and any run without NPM_TRUST_TOKEN
// only read the public package document. They do not call
// GET /-/package/{package}/trust. That GET needs a granular write token and
// often npm-otp. Do not store that token in Actions.
//
// Outside Actions, NPM_TRUST_TOKEN opts into the publisher check:
//   NPM_TRUST_TOKEN=... node scripts/check-npm-trusted-publishers.mjs
//
// Operators confirm Trusted Publishing locally after npm login:
//   npm trust list @edgesentry/ontographia --json

import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const REGISTRY = (process.env.ONTOGRAPHIA_NPM_REGISTRY || "https://registry.npmjs.org").replace(
  /\/+$/,
  "",
);
const USER_AGENT = "ontographia-release-check (+https://github.com/edgesentry/ontographia)";
const SETUP_NODE_DUMMY_TOKEN = "XXXXX-XXXXX-XXXXX-XXXXX";
const EXPECTED_REPO = "edgesentry/ontographia";
const EXPECTED_FILE = "release.yml";

export const PACKAGES = [
  "@edgesentry/ontographia",
  "@edgesentry/ontographia-linux-x64",
  "@edgesentry/ontographia-linux-arm64",
  "@edgesentry/ontographia-darwin-arm64",
  "@edgesentry/ontographia-win32-x64",
];

export const LOCAL_VERIFY_STEPS = `CI does not call GET /-/package/{package}/trust.
Release check does not read NPM_TRUST_TOKEN. Do not store a granular token, a
Bypass-2fa token, or NPM_TOKEN in GitHub Actions. npm publish uses Trusted
Publishing (OIDC) only in the Release job publish-npm.

Confirm locally after npm login:
  npm trust list @edgesentry/ontographia --json
  npm trust list @edgesentry/ontographia-linux-x64 --json
  npm trust list @edgesentry/ontographia-linux-arm64 --json
  npm trust list @edgesentry/ontographia-darwin-arm64 --json
  npm trust list @edgesentry/ontographia-win32-x64 --json

Expected on each package: type github, repository edgesentry/ontographia,
workflow filename release.yml, empty environment, and createPackage
(Allow npm publish on).
`;

export const FIX_STEPS = `${LOCAL_VERIFY_STEPS}
Access pages, if a publisher is missing or does not allow npm publish:
  @edgesentry/ontographia
    https://www.npmjs.com/package/@edgesentry/ontographia/access
  @edgesentry/ontographia-linux-x64
    https://www.npmjs.com/package/@edgesentry/ontographia-linux-x64/access
  @edgesentry/ontographia-linux-arm64
    https://www.npmjs.com/package/@edgesentry/ontographia-linux-arm64/access
  @edgesentry/ontographia-darwin-arm64
    https://www.npmjs.com/package/@edgesentry/ontographia-darwin-arm64/access
  @edgesentry/ontographia-win32-x64
    https://www.npmjs.com/package/@edgesentry/ontographia-win32-x64/access

On each access page, open Settings → Trusted publishing and save that
connection. createStagedPackage alone is not enough: turn Allow npm publish
on. A publisher created after 2026-09-03 allows npm stage publish until you
also allow direct npm publish. Do not upload a Release tarball and do not
run scripts/publish-npm.sh.

Optional local read of the trust API, outside GitHub Actions. A stored
Actions token cannot answer an npm-otp challenge. Do not put this token in
the Release or Release check workflow.
  NPM_TRUST_TOKEN=... node scripts/check-npm-trusted-publishers.mjs
  NPM_TRUST_TOKEN=... NPM_TRUST_OTP=123456 node scripts/check-npm-trusted-publishers.mjs
`;

function isGithub(config) {
  const type = String(config?.type || config?.provider || "").toLowerCase();
  return type === "github" || type === "github-actions";
}

function configRepo(config) {
  const claims = config?.claims && typeof config.claims === "object" ? config.claims : {};
  const direct = [config?.repository, claims.repository].find(
    (value) => typeof value === "string" && value.includes("/"),
  );
  if (direct) return direct;
  const owner = config?.repository_owner || claims.repository_owner || "";
  const name = [config?.repository, claims.repository].find(
    (value) => typeof value === "string" && value.length > 0 && !value.includes("/"),
  );
  if (owner && name) return `${owner}/${name}`;
  if (typeof config?.repository === "string") return config.repository;
  if (typeof claims.repository === "string") return claims.repository;
  return "";
}

function configFile(config) {
  const claims = config?.claims && typeof config.claims === "object" ? config.claims : {};
  const ref = claims.workflow_ref && typeof claims.workflow_ref === "object" ? claims.workflow_ref : {};
  const value =
    config?.file ||
    config?.workflow ||
    config?.workflow_filename ||
    config?.workflowFilename ||
    ref.file ||
    claims.workflow_filename ||
    claims.file ||
    "";
  return typeof value === "string" ? value : "";
}

function configEnvironment(config) {
  const claims = config?.claims && typeof config.claims === "object" ? config.claims : {};
  const value = config?.environment ?? claims.environment ?? "";
  if (value == null) return "";
  if (typeof value === "string") return value.trim();
  return JSON.stringify(value);
}

function permissionsOf(config) {
  if (Array.isArray(config?.permissions)) return config.permissions.map(String);
  const claims = config?.claims;
  if (claims && Array.isArray(claims.permissions)) return claims.permissions.map(String);
  return [];
}

export function extractPublishers(body) {
  if (Array.isArray(body)) return body.filter((item) => item && typeof item === "object");
  if (!body || typeof body !== "object") return [];
  for (const key of ["objects", "trustedPublishers", "publishers", "configs", "items"]) {
    if (Array.isArray(body[key])) return body[key].filter((item) => item && typeof item === "object");
  }
  if (body.type || body.provider || body.claims) return [body];
  return [];
}

function describeConfig(config) {
  const perms = permissionsOf(config);
  return `type=${config?.type || config?.provider || "?"} repository=${configRepo(config) || "?"} file=${configFile(config) || "?"} environment=${configEnvironment(config) || "<empty>"} permissions=${perms.join(",") || "<none>"}`;
}

export function evaluatePublishers(configs) {
  const list = Array.isArray(configs) ? configs.filter((item) => item && typeof item === "object") : [];
  if (list.length === 0) {
    return { ok: false, detail: "no trusted publisher is saved on this package" };
  }
  const github = list.filter(isGithub);
  if (github.length === 0) {
    return {
      ok: false,
      detail: `no GitHub Actions publisher (found ${list.map(describeConfig).join("; ")})`,
    };
  }
  const repo = github.filter((config) => configRepo(config) === EXPECTED_REPO);
  if (repo.length === 0) {
    const found = [...new Set(github.map(configRepo))].join(", ") || "<missing>";
    return {
      ok: false,
      detail: `repository is ${found}; want ${EXPECTED_REPO}`,
    };
  }
  const file = repo.filter((config) => configFile(config) === EXPECTED_FILE);
  if (file.length === 0) {
    const found = [...new Set(repo.map(configFile))].join(", ") || "<missing>";
    return {
      ok: false,
      detail: `workflow filename is ${found}; want ${EXPECTED_FILE}. npm matches the filename, including .yml`,
    };
  }
  const noEnv = file.filter((config) => configEnvironment(config) === "");
  if (noEnv.length === 0) {
    const found = [...new Set(file.map(configEnvironment))].join(", ");
    return {
      ok: false,
      detail: `environment is ${found}; leave the environment name empty. Release does not set a GitHub environment`,
    };
  }
  const allowed = noEnv.filter((config) => permissionsOf(config).includes("createPackage"));
  if (allowed.length === 0) {
    const found = [...new Set(noEnv.flatMap(permissionsOf))].join(", ") || "<none>";
    return {
      ok: false,
      detail: `permissions are ${found}. Allow npm publish is off. createPackage is required; createStagedPackage alone cannot run npm publish`,
    };
  }
  return { ok: true, detail: describeConfig(allowed[0]) };
}

// Authenticated trust reads are local-only. Actions always skips them, even
// when NPM_TRUST_TOKEN is present, so a 401/403/OTP cannot fail Release check.
export function readsTrustedPublishers(env = process.env) {
  if (String(env.GITHUB_ACTIONS || "") === "true") return false;
  return Boolean(String(env.NPM_TRUST_TOKEN || "").trim());
}

export function credentialProblem(env = process.env) {
  if (env.NPM_TOKEN) {
    return (
      "error: NPM_TOKEN is set.\n" +
      "This check does not publish and does not read NPM_TOKEN.\n" +
      "Unset NPM_TOKEN. npm publish uses GitHub Actions OIDC in the Release job.\n" +
      "scripts/publish-npm.sh exits when NPM_TOKEN is set, including on the Release job."
    );
  }
  const nodeAuth = env.NODE_AUTH_TOKEN || "";
  if (nodeAuth && nodeAuth !== SETUP_NODE_DUMMY_TOKEN) {
    return (
      "error: NODE_AUTH_TOKEN is set.\n" +
      "This check does not publish. Unset NODE_AUTH_TOKEN.\n" +
      "The setup-node placeholder (XXXXX-XXXXX-XXXXX-XXXXX) is ignored. A real token is not.\n" +
      "GitHub Actions does not read trusted publisher settings. Locally, use npm trust list."
    );
  }
  return "";
}

function encodePackage(name) {
  return encodeURIComponent(name);
}

async function getJson(url, headers) {
  const response = await fetch(url, {
    headers,
    redirect: "follow",
    signal: AbortSignal.timeout(20_000),
  });
  const text = await response.text();
  let body = text;
  try {
    body = JSON.parse(text);
  } catch {
    body = text;
  }
  return { status: response.status, body, text };
}

function publicHeaders() {
  return { accept: "application/json", "user-agent": USER_AGENT };
}

function authHeaders(token, otp) {
  const headers = publicHeaders();
  if (token) headers.authorization = `Bearer ${token}`;
  if (otp) headers["npm-otp"] = otp;
  return headers;
}

function isAuthStatus(status) {
  return status === 401 || status === 403;
}

function isOtpChallenge(status, text) {
  if (!isAuthStatus(status)) return false;
  if (/bearer token authorization is required/i.test(text)) return false;
  return /npm-otp|one-time password|\botp\b|two-factor|2fa|"tfa"\s*:\s*true/i.test(text);
}

function bodyMessage(body, text) {
  if (body && typeof body === "object" && typeof body.message === "string") return body.message;
  const flat = (text || "").replace(/\s+/g, " ").trim();
  return flat.slice(0, 240);
}

function latestVersion(body) {
  if (!body || typeof body !== "object") return "";
  const tags = body["dist-tags"];
  if (tags && typeof tags.latest === "string") return tags.latest;
  return "";
}

function isDirectRun() {
  const entry = process.argv[1];
  if (!entry) return false;
  return import.meta.url === pathToFileURL(resolve(entry)).href;
}

function warnSkippedTrust(env = process.env) {
  console.error(LOCAL_VERIFY_STEPS.trimEnd());
  if (String(env.GITHUB_ACTIONS || "") === "true" && String(env.NPM_TRUST_TOKEN || "").trim()) {
    console.error(
      "warning: NPM_TRUST_TOKEN is set and ignored in GitHub Actions. Do not store a trust token in Actions.",
    );
  }
}

async function main() {
  const blocked = credentialProblem();
  if (blocked) {
    console.error(blocked);
    process.exit(1);
  }

  const readTrust = readsTrustedPublishers();
  const token = readTrust ? (process.env.NPM_TRUST_TOKEN || "").trim() : "";
  const otp = readTrust ? (process.env.NPM_TRUST_OTP || "").trim() : "";
  const failures = [];
  let sawOtp = false;

  for (const name of PACKAGES) {
    const encoded = encodePackage(name);
    const docUrl = `${REGISTRY}/${encoded}`;
    let doc;
    try {
      doc = await getJson(docUrl, publicHeaders());
    } catch (err) {
      failures.push(
        `${name}: registry ${REGISTRY} did not answer (${err instanceof Error ? err.message : String(err)})`,
      );
      continue;
    }
    if (doc.status === 404) {
      failures.push(
        `${name}: package is not on the registry (HTTP 404). Create it with a placeholder version other than the Cargo.toml version, using an interactive npm login, so the Trusted Publisher form exists. Do not publish the Release tarball.`,
      );
      continue;
    }
    if (doc.status !== 200) {
      failures.push(
        `${name}: public package document returned HTTP ${doc.status} (${bodyMessage(doc.body, doc.text)})`,
      );
      continue;
    }
    const latest = latestVersion(doc.body);
    console.log(`${name} is on the registry${latest ? ` (latest ${latest})` : ""}`);

    if (!readTrust) continue;

    const trustUrl = `${REGISTRY}/-/package/${encoded}/trust`;
    let trust;
    try {
      trust = await getJson(trustUrl, publicHeaders());
    } catch (err) {
      failures.push(
        `${name}: trusted publisher list did not answer (${err instanceof Error ? err.message : String(err)})`,
      );
      continue;
    }
    if (isAuthStatus(trust.status)) {
      try {
        trust = await getJson(trustUrl, authHeaders(token, otp));
      } catch (err) {
        failures.push(
          `${name}: authenticated trusted publisher list did not answer (${err instanceof Error ? err.message : String(err)})`,
        );
        continue;
      }
    }
    if (isOtpChallenge(trust.status, trust.text)) {
      sawOtp = true;
      failures.push(
        `${name}: npm asked for npm-otp (HTTP ${trust.status}: ${bodyMessage(trust.body, trust.text)}). A stored token cannot complete an interactive 2FA challenge. Run npm trust list locally.`,
      );
      continue;
    }
    if (isAuthStatus(trust.status)) {
      failures.push(
        `${name}: GET /-/package/${encoded}/trust returned HTTP ${trust.status} (${bodyMessage(trust.body, trust.text)}).`,
      );
      continue;
    }
    if (trust.status === 404) {
      failures.push(`${name}: trusted publisher list returned HTTP 404. No publisher is saved.`);
      continue;
    }
    if (trust.status !== 200) {
      failures.push(
        `${name}: trusted publisher list returned HTTP ${trust.status} (${bodyMessage(trust.body, trust.text)})`,
      );
      continue;
    }
    const decision = evaluatePublishers(extractPublishers(trust.body));
    if (!decision.ok) {
      failures.push(`${name}: ${decision.detail}`);
      continue;
    }
    console.log(`trusted publisher ok: ${name} ${decision.detail}`);
  }

  if (!readTrust) {
    if (failures.length > 0) {
      console.error("error: npm package presence check failed.");
      for (const failure of failures) console.error(`  - ${failure}`);
      process.exit(1);
    }
    warnSkippedTrust();
    console.log("npm packages on registry; trusted publisher settings were not read");
    return;
  }

  if (failures.length > 0) {
    console.error("error: npm Trusted Publisher check failed.");
    for (const failure of failures) console.error(`  - ${failure}`);
    console.error("");
    console.error(FIX_STEPS);
    if (sawOtp) {
      console.error(
        "This run hit an npm-otp challenge. Release check cannot prompt for a code. Use npm trust list locally.",
      );
    }
    process.exit(1);
  }
  console.log("npm trusted publishers ok");
}

if (isDirectRun()) {
  main().catch((err) => {
    console.error(err instanceof Error ? err.message : String(err));
    process.exit(1);
  });
}
