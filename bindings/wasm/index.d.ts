export interface BuildResult {
  /** Cypher 25, Cypher 5, or GQL text with `$param_N` placeholders. */
  query: string;
  /** Bound parameter values keyed by placeholder name. */
  params: Record<string, unknown>;
}

export interface BuildOptions {
  /** `cypher25` (default), `cypher5`, or `gql`. */
  dialect?: string;
  /** Adapter detection hint, for example `plm.native.yaml`. */
  ontologyPathHint?: string | null;
}

export type WasmSource =
  | string
  | URL
  | Response
  | Uint8Array
  | ArrayBuffer
  | ArrayBufferView;

export interface OntographiaWasm {
  /** Raw ABI version exported by the module. Currently `1`. */
  abiVersion: number;
  /**
   * Compile ontology bytes and an Intent into parameter-bound Cypher.
   *
   * Argument validation and Cypher emission happen in the Rust core; this
   * binding only marshals bytes across the WebAssembly boundary.
   */
  buildCypher(
    ontology: Uint8Array | ArrayBuffer | ArrayBufferView | string,
    intent: object | string,
    options?: BuildOptions,
  ): BuildResult;
}

/** Error raised for Ontographia validation/build failures. */
export class OntographiaWasmError extends Error {
  constructor(message: string);
}

/**
 * Instantiate the module.
 *
 * The default source is `ontographia_wasm.wasm` next to this module and is
 * fetched from the same origin. Pass bytes or a bundler-provided URL to choose
 * the source explicitly.
 */
export function loadOntographia(source?: WasmSource): Promise<OntographiaWasm>;
