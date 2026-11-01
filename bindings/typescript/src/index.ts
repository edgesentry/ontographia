import { readFileSync } from "node:fs";

import { OntographiaError, errorMessage } from "./errors.js";
import { invokeBuild, toOntologyBuffer } from "./ffi.js";
import type { BuildResult, IntentInput } from "./types.js";

export { OntographiaError } from "./errors.js";
export type {
  AggregateFn,
  BuildResult,
  Dialect,
  Direction,
  FilterExpr,
  FilterOp,
  Intent,
  IntentInput,
  JsonValue,
  NodeRef,
  OrderBy,
  ReturnItem,
  TraverseStep,
} from "./types.js";

function intentToJson(intent: IntentInput): string {
  if (typeof intent === "string") return intent;
  return JSON.stringify(intent);
}

function normalizeDialect(dialect: string | undefined): string {
  if (dialect === undefined) return "cypher25";
  return dialect;
}

/**
 * Compile ontology bytes (or UTF-8 text) and an Intent into Cypher.
 *
 * Pass `ontologyPathHint` when the format depends on the file name
 * (for example `manufacturing.native.yaml`). Omit it only when the bytes
 * are enough for adapter detection.
 *
 * `dialect` defaults to `cypher25`.
 */
export function buildCypher(
  ontology: Uint8Array | string,
  intent: IntentInput,
  dialect?: string,
  ontologyPathHint?: string | null,
): BuildResult {
  return invokeBuild(
    toOntologyBuffer(ontology),
    intentToJson(intent),
    normalizeDialect(dialect),
    ontologyPathHint ?? null,
  );
}

/**
 * Read an ontology file and compile an Intent into Cypher.
 * The file path is forwarded as the FFI path hint.
 */
export function buildCypherFromFiles(
  ontologyPath: string,
  intent: IntentInput,
  dialect?: string,
): BuildResult {
  let bytes: Buffer;
  try {
    bytes = readFileSync(ontologyPath);
  } catch (err) {
    throw new OntographiaError(
      `failed to read ontology ${ontologyPath}: ${errorMessage(err)}`,
    );
  }
  return invokeBuild(
    bytes,
    intentToJson(intent),
    normalizeDialect(dialect),
    ontologyPath,
  );
}

/**
 * Ontology held in memory. `build` calls the same FFI entry point as
 * `buildCypher` — validation and emission stay in Rust.
 */
export class Engine {
  readonly #ontology: Buffer;
  readonly #pathHint: string | null;

  private constructor(ontology: Buffer, pathHint: string | null) {
    this.#ontology = ontology;
    this.#pathHint = pathHint;
  }

  /** Read `path` and remember it as the format-detection hint. */
  static load(path: string): Engine {
    let bytes: Buffer;
    try {
      bytes = readFileSync(path);
    } catch (err) {
      throw new OntographiaError(
        `failed to read ontology ${path}: ${errorMessage(err)}`,
      );
    }
    return new Engine(bytes, path);
  }

  /** Copy `data`. Pass `pathHint` when detection needs a file name. */
  static fromBytes(
    data: Uint8Array | string,
    pathHint?: string | null,
  ): Engine {
    return new Engine(toOntologyBuffer(data), pathHint ?? null);
  }

  build(intent: IntentInput, dialect?: string): BuildResult {
    return invokeBuild(
      this.#ontology,
      intentToJson(intent),
      normalizeDialect(dialect),
      this.#pathHint,
    );
  }
}
