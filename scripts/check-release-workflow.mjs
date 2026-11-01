#!/usr/bin/env node
// Release workflow invariants for npm Trusted Publishing and gh release upload.
// Reads .github/workflows/release.yml. Does not run the workflow.
//
//   node scripts/check-release-workflow.mjs
//   node scripts/check-release-workflow.mjs --file path/to/copy.yml

import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const defaultPath = join(repoRoot, ".github", "workflows", "release.yml");

function stripQuotes(value) {
  const text = value.trim();
  if (
    (text.startsWith('"') && text.endsWith('"')) ||
    (text.startsWith("'") && text.endsWith("'"))
  ) {
    return text.slice(1, -1);
  }
  return text;
}

export function splitWorkflow(text) {
  const lines = text.split(/\r?\n/);
  let name = "";
  let inJobs = false;
  /** @type {Map<string, string[]>} */
  const jobs = new Map();
  let current = null;
  for (const line of lines) {
    if (!inJobs) {
      if (/^jobs:\s*(?:#.*)?$/.test(line)) {
        inJobs = true;
        continue;
      }
      const match = line.match(/^name:\s*(.*?)\s*(?:#.*)?$/);
      if (match && !name) name = stripQuotes(match[1]);
      continue;
    }
    const job = line.match(/^  ([A-Za-z0-9_-]+):\s*(?:#.*)?$/);
    if (job) {
      current = job[1];
      jobs.set(current, []);
      continue;
    }
    if (current) jobs.get(current).push(line);
  }
  return { name, jobs, inJobs };
}

function jobBody(jobs, id) {
  const lines = jobs.get(id);
  return lines ? lines.join("\n") : "";
}

export function hasCheckout(jobText) {
  if (/^[ \t]*-\s*uses:\s*\S*actions\/checkout(?:@|\s|$)/m.test(jobText)) return true;
  if (/^[ \t]*-\s*uses:\s*\S+\/checkout(?:@|\s|$)/m.test(jobText)) return true;
  return /^[ \t]*(?:-\s*)?run:.*\bgit\s+clone\b/m.test(jobText);
}

export function workflowProblems(text) {
  const problems = [];
  const { name, jobs, inJobs } = splitWorkflow(text);
  if (!inJobs) problems.push("workflow has no top-level jobs: block");
  if (name !== "Release") {
    problems.push(
      `workflow name is ${name || "<missing>"}; npm Trusted Publishing is tied to the workflow name Release`,
    );
  }
  if (!jobs.has("publish-npm")) {
    problems.push(
      "job id publish-npm is missing. scripts/publish-npm.sh refuses to run unless GITHUB_JOB=publish-npm. Do not rename that job id.",
    );
  } else {
    const body = jobBody(jobs, "publish-npm");
    if (!/^[ \t]*id-token:\s*write\s*(?:#.*)?$/m.test(body)) {
      problems.push(
        "job publish-npm must set permissions id-token: write. A job permissions block replaces the workflow permissions, and npm Trusted Publishing needs that OIDC token.",
      );
    }
    if (/^    environment\s*:/m.test(body)) {
      problems.push(
        "job publish-npm sets a GitHub environment. The trusted publisher environment name must stay empty, and Release is started with Run workflow on release.yml.",
      );
    }
  }
  if (!jobs.has("upload-assets")) {
    problems.push("job id upload-assets is missing");
  } else {
    const body = jobBody(jobs, "upload-assets");
    if (!hasCheckout(body)) {
      problems.push(
        "job upload-assets must check out the repo (actions/checkout, or an equivalent git clone). gh release upload exits \"fatal: not a git repository\" without a checkout.",
      );
    }
    if (!/^[ \t]*GH_REPO\s*:/m.test(body)) {
      problems.push(
        "job upload-assets must set GH_REPO (owner/repo) on the gh release upload step. gh uses it when git remote detection fails.",
      );
    }
    if (!/\bgh\s+release\s+upload\b/.test(body)) {
      problems.push("job upload-assets must run gh release upload");
    }
  }
  return problems;
}

function usage() {
  console.log(`Usage: node scripts/check-release-workflow.mjs [--file PATH]

  Default PATH is .github/workflows/release.yml.
  The workflow file name, workflow name Release, and job id publish-npm are
  npm Trusted Publishing / OIDC invariants. upload-assets must checkout and set GH_REPO.
`);
}

function parseArgs(argv) {
  let file = defaultPath;
  let explicit = false;
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--file") {
      file = argv[++i] ?? "";
      explicit = true;
      if (!file) throw new Error("--file requires a path");
    } else if (arg === "-h" || arg === "--help") {
      usage();
      process.exit(0);
    } else {
      throw new Error(`unknown argument: ${arg}`);
    }
  }
  return { file: resolve(file), explicit };
}

function isDirectRun() {
  const entry = process.argv[1];
  if (!entry) return false;
  return import.meta.url === pathToFileURL(resolve(entry)).href;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.explicit && args.file !== defaultPath) {
    console.error(`error: refusing to check ${args.file}`);
    console.error("The Release workflow file must stay .github/workflows/release.yml.");
    process.exit(1);
  }
  let text;
  try {
    text = readFileSync(args.file, "utf8");
  } catch (err) {
    const code = err && typeof err === "object" && "code" in err ? err.code : "";
    if (code === "ENOENT" && !args.explicit) {
      console.error("error: .github/workflows/release.yml is missing.");
      console.error(
        "npm Trusted Publishing matches the workflow filename release.yml (including .yml).",
      );
      console.error(
        "Do not rename it. The workflow name must stay Release and the job id must stay publish-npm.",
      );
      process.exit(1);
    }
    throw err;
  }
  const problems = workflowProblems(text);
  if (problems.length > 0) {
    console.error(`error: ${args.explicit ? args.file : ".github/workflows/release.yml"}`);
    for (const problem of problems) console.error(`  - ${problem}`);
    process.exit(1);
  }
  const shown = args.explicit ? args.file : ".github/workflows/release.yml";
  console.log(`release workflow ok: ${shown} name=Release job=publish-npm`);
}

if (isDirectRun()) {
  try {
    main();
  } catch (err) {
    console.error(err instanceof Error ? err.message : String(err));
    process.exit(1);
  }
}
