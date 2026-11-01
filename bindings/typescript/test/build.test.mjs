import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import {
  Engine,
  OntographiaError,
  buildCypher,
  buildCypherFromFiles,
} from "../dist/index.js";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..", "..");
const ontologyPath = join(repoRoot, "examples", "manufacturing.native.yaml");

function sampleIntent() {
  return JSON.parse(
    readFileSync(join(repoRoot, "examples", "sample_intent.json"), "utf8"),
  );
}

describe("buildCypherFromFiles", () => {
  it("builds Cypher 25 for the manufacturing sample", () => {
    const result = buildCypherFromFiles(ontologyPath, sampleIntent(), "cypher25");
    assert.ok(result.query.startsWith("CYPHER 25"), result.query);
    assert.ok(
      result.query.includes("FILTER product.sku = $param_0"),
      result.query,
    );
    assert.equal(result.params.param_0, "SPX-100");
  });

  it("emits Cypher 5 with WHERE", () => {
    const result = buildCypherFromFiles(ontologyPath, sampleIntent(), "cypher5");
    assert.ok(result.query.startsWith("CYPHER 5"), result.query);
    assert.ok(result.query.includes("WHERE "), result.query);
  });

  it("defaults a missing dialect to cypher25", () => {
    const result = buildCypherFromFiles(ontologyPath, sampleIntent());
    assert.ok(result.query.startsWith("CYPHER 25"), result.query);
  });

  it("rejects an unknown dialect", () => {
    assert.throws(
      () => buildCypherFromFiles(ontologyPath, sampleIntent(), "cyhper5"),
      (err) => {
        assert.ok(err instanceof OntographiaError);
        assert.match(err.message, /unknown dialect 'cyhper5'/);
        return true;
      },
    );
  });

  it("rejects an unknown Intent key", () => {
    const intent = JSON.stringify(sampleIntent()).replace(
      '"filter"',
      '"filters"',
    );
    assert.throws(
      () => buildCypherFromFiles(ontologyPath, intent, "cypher25"),
      (err) => {
        assert.ok(err instanceof OntographiaError);
        assert.match(err.message, /unknown field/);
        assert.match(err.message, /filters/);
        return true;
      },
    );
  });

  it("reports a missing ontology file", () => {
    assert.throws(
      () => buildCypherFromFiles(join(repoRoot, "examples", "no-such.yaml"), "{}"),
      (err) => {
        assert.ok(err instanceof OntographiaError);
        assert.match(err.message, /failed to read ontology/);
        return true;
      },
    );
  });
});

describe("Engine", () => {
  it("load().build() matches buildCypherFromFiles", () => {
    const fromFiles = buildCypherFromFiles(ontologyPath, sampleIntent());
    const fromEngine = Engine.load(ontologyPath).build(sampleIntent());
    assert.equal(fromEngine.query, fromFiles.query);
    assert.deepEqual(fromEngine.params, fromFiles.params);
  });

  it("fromBytes uses the path hint", () => {
    const bytes = readFileSync(ontologyPath);
    const result = buildCypher(bytes, sampleIntent(), "cypher25", ontologyPath);
    const viaEngine = Engine.fromBytes(bytes, ontologyPath).build(sampleIntent(), "cypher25");
    assert.equal(viaEngine.query, result.query);
    assert.equal(result.params.param_0, "SPX-100");
  });
});
