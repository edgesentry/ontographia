/**
 * Spike loader: re-export the canonical npm-package binding and default the
 * module source to the `.wasm` file built next to this demo page.
 *
 * Package source: bindings/wasm/index.js (@edgesentry/ontographia-wasm).
 */
import {
  loadOntographia as loadPackage,
  OntographiaWasmError,
} from "../../../../bindings/wasm/index.js";

export { OntographiaWasmError };

export function loadOntographia(
  source = new URL("./ontographia_wasm.wasm", import.meta.url),
) {
  return loadPackage(source);
}
