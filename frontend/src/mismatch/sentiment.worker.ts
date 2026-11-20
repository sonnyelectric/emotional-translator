/// <reference lib="webworker" />
/**
 * Web Worker: in-browser text sentiment (display-only mismatch feature).
 * Model: Xenova/distilbert-base-uncased-finetuned-sst-2-english, q8 (model_quantized.onnx).
 * Messages in:  {type:'init'} | {type:'classify', id:string, text:string}
 * Messages out: {type:'ready'} | {type:'unavailable', reason:string} | {type:'result', id, label, score}
 * Any failure (offline, blocked, WASM error) posts 'unavailable' once; it never throws.
 */
import { pipeline, env } from '@huggingface/transformers';

export const MODEL_ID = 'Xenova/distilbert-base-uncased-finetuned-sst-2-english';

type Classifier = (text: string) => Promise<Array<{ label: string; score: number }>>;

let loading: Promise<Classifier | null> | null = null;
const ctx = self as unknown as DedicatedWorkerGlobalScope;

function load(): Promise<Classifier | null> {
  if (!loading) {
    loading = (async () => {
      try {
        env.allowLocalModels = true; // lets an optional public/models/ bundle win when present
        const c = (await pipeline('sentiment-analysis', MODEL_ID, { dtype: 'q8' })) as unknown as Classifier;
        ctx.postMessage({ type: 'ready' });
        return c;
      } catch (e) {
        ctx.postMessage({ type: 'unavailable', reason: String((e as Error)?.message ?? e) });
        return null;
      }
    })();
  }
  return loading;
}

ctx.onmessage = async (ev: MessageEvent) => {
  const m = ev.data;
  if (m?.type === 'init') {
    void load();
  } else if (m?.type === 'classify') {
    const c = await load();
    if (!c) return;
    try {
      const out = await c(String(m.text));
      ctx.postMessage({ type: 'result', id: m.id, label: out[0].label, score: out[0].score });
    } catch {
      /* skip this segment; feature stays quiet */
    }
  }
};
