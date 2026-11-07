/**
 * Demo page: Intent + ontology -> Cypher 25 + params, compiled in the browser.
 *
 * Nothing is precomputed and no server-side engine is involved: every chip
 * click re-fetches the fixed Intent JSON and compiles it with the WebAssembly
 * build of the same Ontographia core used by the native CLI.
 */

import { OntographiaWasmError, loadOntographia } from "./ontographia-wasm.js";

/** Repo root, resolved from this module so any static-server root works. */
const REPO_ROOT = new URL("../../../../", import.meta.url);
const ONTOLOGY_PATH = "examples/plm/plm.native.yaml";
const ONTOLOGY_HINT = "plm.native.yaml";
const CHIPS_PATH = "examples/plm/chips.json";

const STRINGS = {
  ja: {
    title: "Ontographia ブラウザスパイク",
    subtitle:
      "Intent とオントロジーから Cypher 25 をブラウザ内の WebAssembly で生成します。サーバー呼び出しも LLM も使いません。",
    questions: "固定チップ",
    output: "生成結果",
    cypher: "Cypher 25",
    params: "パラメータ",
    loading: "読み込み中…",
    ready: "準備完了",
    compiling: "コンパイル中…",
    failed: "エラー",
    engine: "ontographia-wasm ABI v{version}",
    size: "{raw} KiB（gzip {gzip} KiB）",
    noWasm:
      "WASM を読み込めませんでした。先に scripts/build-wasm.sh を実行し、リポジトリルートを静的サーバーで配信してください。",
    empty: "—",
    sourceNote: "ビルド元: {path}",
  },
  en: {
    title: "Ontographia browser spike",
    subtitle:
      "Compile Intent + ontology into Cypher 25 inside the browser with WebAssembly. No server call, no LLM.",
    questions: "Fixed chips",
    output: "Generated output",
    cypher: "Cypher 25",
    params: "Parameters",
    loading: "Loading…",
    ready: "Ready",
    compiling: "Compiling…",
    failed: "Error",
    engine: "ontographia-wasm ABI v{version}",
    size: "{raw} KiB (gzip {gzip} KiB)",
    noWasm:
      "Could not load the WASM build. Run scripts/build-wasm.sh first and serve the repository root over a static server.",
    empty: "—",
    sourceNote: "Source: {path}",
  },
};

const params = new URLSearchParams(location.search);
let locale = params.get("lang") === "en" ? "en" : params.get("lang") === "ja" ? "ja" : null;
if (locale === null) {
  locale = (navigator.language || "en").toLowerCase().startsWith("ja") ? "ja" : "en";
}
const initialChipId = params.get("chip");

const elements = {
  langToggle: document.querySelector("#lang"),
  chipList: document.querySelector("#chip-list"),
  query: document.querySelector("#query code"),
  params: document.querySelector("#params code"),
  timing: document.querySelector("#timing"),
  error: document.querySelector("#error"),
  engine: document.querySelector("#engine"),
  sourceNote: document.querySelector("#source-note"),
};

let engine = null;
let ontologyBytes = null;
let chips = [];
let selectedChipId = null;

function t(key, values = {}) {
  let text = STRINGS[locale][key] ?? key;
  for (const [name, value] of Object.entries(values)) {
    text = text.replaceAll(`{${name}}`, String(value));
  }
  return text;
}

function applyLocale() {
  document.documentElement.lang = locale;
  document.title = t("title");
  for (const node of document.querySelectorAll("[data-i18n]")) {
    node.textContent = t(node.dataset.i18n);
  }
  elements.langToggle.textContent = locale === "ja" ? "English" : "日本語";
  elements.langToggle.setAttribute("aria-label", locale === "ja" ? "Switch to English" : "日本語に切り替える");
  if (engine === null) {
    elements.engine.textContent = t("loading");
  } else {
    renderEngineLabel();
  }
  renderChips();
}

function renderEngineLabel() {
  const parts = [t("engine", { version: engine.abiVersion })];
  if (engine.size) {
    parts.push(
      t("size", {
        raw: Math.round(engine.size.raw / 102.4) / 10,
        gzip: Math.round(engine.size.gzip / 102.4) / 10,
      }),
    );
  }
  elements.engine.textContent = parts.join(" · ");
}

function renderChips() {
  if (chips.length === 0) return;
  elements.chipList.replaceChildren(
    ...chips.map((chip) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "chip";
      button.dataset.chipId = chip.chip_id;

      const label = document.createElement("span");
      label.className = "chip-label";
      label.textContent = locale === "ja" ? chip.label_ja : chip.label_en;

      const description = document.createElement("span");
      description.className = "chip-description";
      description.textContent = locale === "ja" ? chip.description_ja : chip.description_en;

      button.append(label, description);
      if (chip.chip_id === selectedChipId) {
        button.setAttribute("aria-current", "true");
      }
      button.addEventListener("click", () => {
        for (const other of elements.chipList.querySelectorAll(".chip")) {
          other.removeAttribute("aria-current");
        }
        button.setAttribute("aria-current", "true");
        selectedChipId = chip.chip_id;
        void compileChip(chip);
      });
      return button;
    }),
  );
}

function showError(message) {
  elements.error.hidden = false;
  elements.error.textContent = `${t("failed")}: ${message}`;
}

function clearError() {
  elements.error.hidden = true;
  elements.error.textContent = "";
}

async function fetchJson(path) {
  const response = await fetch(new URL(path, REPO_ROOT));
  if (!response.ok) {
    throw new Error(`${path}: HTTP ${response.status}`);
  }
  return response.json();
}

async function compileChip(chip) {
  if (engine === null) return;
  clearError();
  elements.timing.textContent = t("compiling");
  elements.sourceNote.textContent = t("sourceNote", { path: chip.intent_path });

  try {
    const intentResponse = await fetch(new URL(chip.intent_path, REPO_ROOT));
    if (!intentResponse.ok) {
      throw new Error(`${chip.intent_path}: HTTP ${intentResponse.status}`);
    }
    const intent = await intentResponse.json();

    const started = performance.now();
    const result = engine.buildCypher(ontologyBytes, intent, {
      dialect: "cypher25",
      ontologyPathHint: ONTOLOGY_HINT,
    });
    const elapsed = performance.now() - started;
    const elapsedLabel = elapsed < 0.01 ? "<0.01" : elapsed.toFixed(2);

    elements.query.textContent = result.query;
    elements.params.textContent = JSON.stringify(result.params, null, 2);
    elements.timing.textContent = `${elapsedLabel} ms`;
  } catch (error) {
    elements.query.textContent = t("empty");
    elements.params.textContent = t("empty");
    elements.timing.textContent = "";
    if (error instanceof OntographiaWasmError) {
      showError(error.message);
    } else {
      showError(error instanceof Error ? error.message : String(error));
    }
  }
}

async function loadSize() {
  try {
    const response = await fetch(new URL("./bundle-size.json", import.meta.url));
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

async function main() {
  applyLocale();

  try {
    const [loaded, ontologyResponse, chipList, size] = await Promise.all([
      loadOntographia(),
      fetch(new URL(ONTOLOGY_PATH, REPO_ROOT)),
      fetchJson(CHIPS_PATH),
      loadSize(),
    ]);
    if (!ontologyResponse.ok) {
      throw new Error(`${ONTOLOGY_PATH}: HTTP ${ontologyResponse.status}`);
    }
    ontologyBytes = new Uint8Array(await ontologyResponse.arrayBuffer());
    engine = loaded;
    engine.size = size;
    chips = chipList;
    renderEngineLabel();
    renderChips();
    elements.timing.textContent = t("ready");
    const buttons = [...elements.chipList.querySelectorAll(".chip")];
    const initial = buttons.find((button) => button.dataset.chipId === initialChipId) ?? buttons[0];
    if (initial) initial.click();
  } catch (error) {
    engine = null;
    elements.engine.textContent = t("noWasm");
    showError(error instanceof Error ? error.message : String(error));
  }
}

elements.langToggle.addEventListener("click", () => {
  locale = locale === "ja" ? "en" : "ja";
  const url = new URL(location.href);
  url.searchParams.set("lang", locale);
  history.replaceState(null, "", url);
  applyLocale();
});

window.addEventListener("error", (event) => {
  showError(event.message);
});

void main();
