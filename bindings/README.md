# bindings/

Python (PyO3), Go (cgo), TypeScript (koffi over the C ABI), and browser WASM (`wasm32-unknown-unknown`) wrappers over `Engine.build()`. **Do not reimplement query logic here.**

| Binding | Guide |
|---------|-------|
| Python | [docs/python.md](../docs/python.md) |
| Go | [docs/go.md](../docs/go.md) (module README: [`go/README.md`](go/README.md)) |
| TypeScript / JavaScript | [typescript/README.md](typescript/README.md) (user guide deferred) |
| Browser WASM | [wasm/README.md](wasm/README.md) (npm `@edgesentry/ontographia-wasm`; [docs/wasm.md](../docs/wasm.md)) |

Demo: [`go/cmd/demo/main.go`](go/cmd/demo/main.go), [`typescript/examples/demo.mjs`](typescript/examples/demo.mjs), [`examples/plm/browser-spike`](../examples/plm/browser-spike/README.md)
