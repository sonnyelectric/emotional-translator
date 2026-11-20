import { useEffect, useMemo, useRef, useState } from 'react';
import type { AnnotationMap, MismatchResult, Segment } from '../visual/contract';
import { computeMismatch, type TextSentiment } from './valence';

export type MismatchStatus = 'off' | 'loading' | 'ready' | 'unavailable';

export interface WorkerLike {
  postMessage(msg: unknown): void;
  terminate(): void;
  onmessage: ((ev: { data: any }) => void) | null;
  onerror: ((ev: unknown) => void) | null;
}

function defaultFactory(): WorkerLike {
  return new Worker(new URL('./sentiment.worker.ts', import.meta.url), { type: 'module' }) as unknown as WorkerLike;
}

/**
 * Words-versus-voice check per committed segment. Display-only: reads segments and
 * annotations, never writes them. Returns an empty map when disabled or when the
 * model cannot load (offline), without throwing.
 */
export function useMismatchWithStatus(
  segments: Segment[],
  annotations: AnnotationMap,
  enabled = true,
  workerFactory: () => WorkerLike = defaultFactory,
): { results: Map<string, MismatchResult>; status: MismatchStatus } {
  const [sentiments, setSentiments] = useState<Record<string, TextSentiment>>({});
  const [status, setStatus] = useState<MismatchStatus>('off');
  const workerRef = useRef<WorkerLike | null>(null);
  const sent = useRef(new Set<string>());

  useEffect(() => {
    if (!enabled) {
      setStatus('off');
      return;
    }
    let w: WorkerLike;
    try {
      w = workerFactory();
    } catch {
      setStatus('unavailable');
      return;
    }
    workerRef.current = w;
    setStatus('loading');
    w.onmessage = (ev) => {
      const m = ev.data;
      if (m?.type === 'ready') setStatus('ready');
      else if (m?.type === 'unavailable') {
        if (import.meta.env.DEV) console.warn('[mismatch] text model unavailable:', m.reason);
        setStatus('unavailable');
      }
      else if (m?.type === 'result') setSentiments((s) => ({ ...s, [m.id]: { label: m.label, score: m.score } }));
    };
    w.onerror = () => setStatus('unavailable');
    try {
      w.postMessage({ type: 'init' });
    } catch {
      setStatus('unavailable');
    }
    return () => {
      w.terminate();
      workerRef.current = null;
      sent.current.clear();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);

  // Classify each committed text once, keyed by segment id plus text.
  useEffect(() => {
    const w = workerRef.current;
    if (!enabled || !w || status === 'unavailable') return;
    for (const s of segments) {
      const key = `${s.segment_id}\u0000${s.text}`;
      if (!s.text.trim() || sent.current.has(key)) continue;
      sent.current.add(key);
      try {
        w.postMessage({ type: 'classify', id: key, text: s.text });
      } catch {
        /* ignore */
      }
    }
  }, [segments, enabled, status]);

  const results = useMemo(() => {
    const out = new Map<string, MismatchResult>();
    if (!enabled || status === 'unavailable') return out;
    const all = Object.values(annotations);
    for (const s of segments) {
      const sentiment = sentiments[`${s.segment_id}\u0000${s.text}`];
      if (!sentiment) continue;
      out.set(
        s.segment_id,
        computeMismatch(s.segment_id, s.text, sentiment, all.filter((a) => a.segment_id === s.segment_id)),
      );
    }
    return out;
  }, [segments, annotations, sentiments, enabled, status]);

  return { results, status };
}

/** Plan contract: useMismatch(segments, annotations) returns Map<segment_id, result>. */
export function useMismatch(segments: Segment[], annotations: AnnotationMap, enabled = true): Map<string, MismatchResult> {
  return useMismatchWithStatus(segments, annotations, enabled).results;
}
