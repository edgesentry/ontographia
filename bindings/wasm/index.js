/**
 * Loader for the `ontographia-wasm` browser module.
 *
 * This file is the whole JavaScript binding: the `.wasm` module has no imports
 * and exports plain functions plus `memory`. Strings are UTF-8; result buffers
 * are `[u32 LE length][payload]`.
 *
 * @typedef {{ query: string, params: Record<string, unknown> }} BuildResult
 * @typedef {{ dialect?: string, ontologyPathHint?: string | null }} BuildOptions
 */

const RESULT_HEADER_BYTES = 4;
const encoder = new TextEncoder();
const decoder = new TextDecoder("utf-8", { fatal: true });

/** Error raised for Ontographia validation/build failures. */
export class OntographiaWasmError extends Error {
  constructor(message) {
    super(message);
    this.name = "OntographiaWasmError";
  }
}

/**
 * Instantiate the module.
 *
 * The default source is `ontographia_wasm.wasm` next to this module, loaded
 * from the same origin. Pass bytes to avoid any fetch (Node, a service worker,
 * or an asset URL produced by a bundler).
 *
 * @param {string | URL | Response | Uint8Array | ArrayBuffer | ArrayBufferView} [source]
 *   URL of the `.wasm` file (default: next to this module), or the module bytes
 *   themselves so non-HTTP hosts such as Node can reuse the same loader.
 * @returns {Promise<{
 *   abiVersion: number,
 *   buildCypher: (ontology: Uint8Array | ArrayBuffer | ArrayBufferView | string,
 *                 intent: object | string,
 *                 options?: BuildOptions) => BuildResult,
 * }>}
 */
export async function loadOntographia(
  source = new URL("./ontographia_wasm.wasm", import.meta.url),
) {
  const { instance } = await WebAssembly.instantiate(await toWasmBytes(source), {});
  const api = instance.exports;

  const memory = () => api.memory;

  /**
   * Copy bytes into linear memory. Re-read `memory().buffer` afterwards: the
   * allocation may have grown the memory.
   */
  function writeInput(bytes) {
    const pointer = api.otg_alloc(bytes.byteLength) >>> 0;
    if (pointer === 0 && bytes.byteLength > 0) {
      throw new Error("otg_alloc returned a null pointer");
    }
    if (bytes.byteLength > 0) {
      new Uint8Array(memory().buffer, pointer, bytes.byteLength).set(bytes);
    }
    return { pointer, length: bytes.byteLength };
  }

  function releaseInput(input) {
    if (input.pointer !== 0 || input.length > 0) {
      api.otg_free_input(input.pointer, input.length);
    }
  }

  function readResult(pointer) {
    const length = new DataView(memory().buffer).getUint32(pointer, true);
    const payload = new Uint8Array(memory().buffer, pointer + RESULT_HEADER_BYTES, length);
    return decoder.decode(payload);
  }

  const abiVersion = api.otg_abi_version() >>> 0;

  /**
   * Compile ontology bytes and an Intent into Cypher 25 + params.
   *
   * @returns {BuildResult}
   */
  function buildCypher(ontology, intent, options = {}) {
    const ontologyBytes = toBytes(ontology, "ontology");
    const intentBytes =
      typeof intent === "string"
        ? encoder.encode(intent)
        : encoder.encode(JSON.stringify(intent));
    const hint = options.ontologyPathHint ?? null;
    const hintBytes = hint === null ? null : encoder.encode(hint);
    const dialectBytes = encoder.encode(options.dialect ?? "cypher25");

    let ontologyInput = null;
    let intentInput = null;
    let hintInput = null;
    let dialectInput = null;

    try {
      // Allocate inside the try so a later failure still frees earlier buffers.
      ontologyInput = writeInput(ontologyBytes);
      intentInput = writeInput(intentBytes);
      if (hintBytes !== null) hintInput = writeInput(hintBytes);
      dialectInput = writeInput(dialectBytes);

      const pointer =
        api.otg_build(
          ontologyInput.pointer,
          ontologyInput.length,
          intentInput.pointer,
          intentInput.length,
          hintInput === null ? 0 : hintInput.pointer,
          hintInput === null ? 0 : hintInput.length,
          dialectInput.pointer,
          dialectInput.length,
        ) >>> 0;

      if (pointer === 0) {
        throw new Error("otg_build returned a null pointer");
      }

      let text;
      try {
        text = readResult(pointer);
      } finally {
        api.otg_free_result(pointer);
      }

      const parsed = JSON.parse(text);
      if (typeof parsed.error === "string") {
        throw new OntographiaWasmError(parsed.error);
      }
      return { query: parsed.query, params: parsed.params };
    } finally {
      if (ontologyInput !== null) releaseInput(ontologyInput);
      if (intentInput !== null) releaseInput(intentInput);
      if (hintInput !== null) releaseInput(hintInput);
      if (dialectInput !== null) releaseInput(dialectInput);
    }
  }

  return { abiVersion, buildCypher };
}

function toBytes(value, label) {
  if (typeof value === "string") return encoder.encode(value);
  if (value instanceof Uint8Array) return value;
  if (value instanceof ArrayBuffer) return new Uint8Array(value);
  if (ArrayBuffer.isView(value)) {
    return new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
  }
  throw new TypeError(`${label} must be a string, Uint8Array, ArrayBuffer, or ArrayBufferView`);
}

async function toWasmBytes(source) {
  if (typeof Response !== "undefined" && source instanceof Response) {
    if (!source.ok) {
      throw new Error(`failed to fetch WASM: HTTP ${source.status}`);
    }
    return new Uint8Array(await source.arrayBuffer());
  }
  if (typeof source === "string" || source instanceof URL) {
    const response = await fetch(source);
    if (!response.ok) {
      throw new Error(`failed to fetch ${source}: HTTP ${response.status}`);
    }
    return new Uint8Array(await response.arrayBuffer());
  }
  return toBytes(source, "WASM source");
}
