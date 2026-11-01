import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { buildCypherFromFiles } from "../dist/index.js";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const ontology = join(repoRoot, "examples", "manufacturing.native.yaml");
const intent = readFileSync(join(repoRoot, "examples", "sample_intent.json"), "utf8");

const result = buildCypherFromFiles(ontology, intent, "cypher25");
console.log(result.query);
console.log(result.params);
