# Dependencies needed by src/visual and src/mismatch

Runtime
- react, react-dom (already in the shell)
- @huggingface/transformers (BC1 adds; used only in src/mismatch/sentiment.worker.ts)

Dev / test
- vitest (unit tests: src/visual/*.test.ts, src/mismatch/*.test.ts, no DOM needed)
- typescript, vite (shell)

Vite note: the worker is created with
`new Worker(new URL('./sentiment.worker.ts', import.meta.url), { type: 'module' })`.
Set `worker: { format: 'es' }` in vite.config if the build complains.

Model: `Xenova/distilbert-base-uncased-finetuned-sst-2-english` (id verified on the Hugging Face API),
dtype `q8` = `onnx/model_quantized.onnx` (about 67.6 MB, downloaded on first use then cached by the browser).
No other dependencies. Radar, clouds and tooltips are hand-rolled SVG/CSS.
