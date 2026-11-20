import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import './visual.css';
import type { Annotation, TranscriptViewProps } from './contract';
import { CloudLayer } from './CloudLayer';
import type { CloudSpec } from './cloudEngine';
import { CATEGORY_SHAPE, lineRuns, sameRuns, type Run } from './geometry';
import { colorFor, GLYPH, LABEL_TEXT } from './palette';
import { MismatchBadge } from '../mismatch/MismatchBadge';

type RunMap = Record<string, Run[]>;

const esc = (s: string) => (typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(s) : s.replace(/["\\]/g, '\\$&'));

export function TranscriptView({
  segments,
  partial,
  annotations,
  settings,
  onInspect,
  mismatch,
  selectedAnnotationId,
}: TranscriptViewProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [runs, setRuns] = useState<RunMap>({});
  const rafRef = useRef(0);

  // Latest annotation per word range, for click and keyboard targets.
  const anns = useMemo(() => Object.values(annotations), [annotations]);

  const measure = useCallback(() => {
    const root = rootRef.current;
    if (!root) return;
    const origin = root.getBoundingClientRect();
    const next: RunMap = {};
    for (const a of anns) {
      const s = root.querySelector(`[data-word-id="${esc(a.start_word_id)}"]`);
      const e = root.querySelector(`[data-word-id="${esc(a.end_word_id)}"]`);
      if (!s || !e) continue;
      const range = document.createRange();
      range.setStartBefore(s);
      range.setEndAfter(e);
      const rects = Array.from(range.getClientRects());
      const r = lineRuns(rects, origin);
      if (r.length) next[a.annotation_id] = r;
    }
    setRuns((prev) => {
      const ka = Object.keys(prev);
      const kb = Object.keys(next);
      if (ka.length === kb.length && kb.every((k) => sameRuns(prev[k], next[k]))) return prev;
      return next;
    });
  }, [anns]);

  // One rAF-debounced measure per frame.
  const schedule = useCallback(() => {
    if (rafRef.current) return;
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = 0;
      measure();
    });
  }, [measure]);

  useLayoutEffect(() => {
    measure();
  }, [measure, segments, partial]);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(schedule) : null;
    ro?.observe(root);
    window.addEventListener('resize', schedule);
    document.fonts?.ready.then(schedule).catch(() => {});
    document.fonts?.addEventListener?.('loadingdone', schedule);
    return () => {
      ro?.disconnect();
      window.removeEventListener('resize', schedule);
      document.fonts?.removeEventListener?.('loadingdone', schedule);
      cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
    };
  }, [schedule]);

  const specs = useMemo<CloudSpec[]>(() => {
    const out: CloudSpec[] = [];
    for (const a of anns) {
      const r = runs[a.annotation_id];
      if (!r) continue;
      const cvd = settings.palette === 'cvd';
      const color = cvd ? colorFor(a.primary, 'cvd') : a.color;
      const sec = a.blend ? a.blend.secondary : null;
      out.push({
        id: a.annotation_id,
        runs: r,
        shape: a.shape ?? CATEGORY_SHAPE[a.primary],
        blendShape: sec ? CATEGORY_SHAPE[sec] : null,
        blendWeight: a.blend ? a.blend.weight : 0,
        color,
        color2: sec ? colorFor(sec, settings.palette) : null,
        opacity: a.opacity,
        intensity: a.visual_intensity,
        finalized: a.state === 'finalized',
        selected: a.annotation_id === selectedAnnotationId,
      });
    }
    return out;
  }, [anns, runs, settings.palette, selectedAnnotationId]);

  // For each word id, the annotation covering it (first match wins; later ones do not steal clicks).
  const wordOwner = useMemo(() => {
    const m = new Map<string, Annotation>();
    for (const seg of segments) {
      if (!seg.words) continue;
      const idx = new Map(seg.words.map((w, i) => [w.word_id, i]));
      for (const a of anns) {
        if (a.segment_id !== seg.segment_id) continue;
        const s = idx.get(a.start_word_id);
        const e = idx.get(a.end_word_id);
        if (s === undefined || e === undefined) continue;
        for (let i = s; i <= e; i++) if (!m.has(seg.words[i].word_id)) m.set(seg.words[i].word_id, a);
      }
    }
    return m;
  }, [segments, anns]);

  const labelRuns = settings.showLabels
    ? anns.filter((a) => runs[a.annotation_id]?.length).map((a) => ({ a, r: runs[a.annotation_id][0] }))
    : [];

  return (
    <div className="et-visual et-transcript" ref={rootRef} data-reduced-motion={settings.reducedMotion || undefined}>
      <CloudLayer specs={specs} reducedMotion={settings.reducedMotion} />
      <div className="et-text">
        {segments.map((seg) => {
          const mm = settings.mismatch ? mismatch?.get(seg.segment_id) : undefined;
          return (
            <p className="et-seg" key={seg.segment_id} data-segment-id={seg.segment_id}>
              {seg.words && seg.words.length ? (
                seg.words.map((w, i) => {
                  const owner = wordOwner.get(w.word_id);
                  const isStart = owner && owner.start_word_id === w.word_id;
                  return (
                    <span key={w.word_id}>
                      {i > 0 ? ' ' : null}
                      <span
                        className={owner ? 'et-word et-word--ann' : 'et-word'}
                        data-word-id={w.word_id}
                        data-annotation-id={owner?.annotation_id}
                        role={isStart ? 'button' : undefined}
                        tabIndex={isStart ? 0 : undefined}
                        aria-label={
                          isStart
                            ? `Vocal cue: ${LABEL_TEXT[owner.primary]}, relative model support ${Math.round(owner.support * 100)} percent. Open details.`
                            : undefined
                        }
                        onClick={owner ? () => onInspect(owner.annotation_id) : undefined}
                        onKeyDown={
                          isStart
                            ? (e) => {
                                if (e.key === 'Enter' || e.key === ' ') {
                                  e.preventDefault();
                                  onInspect(owner.annotation_id);
                                }
                              }
                            : undefined
                        }
                      >
                        {w.text}
                      </span>
                    </span>
                  );
                })
              ) : (
                <span className="et-word et-word--pending">{seg.text}</span>
              )}
              {mm?.differs ? <MismatchBadge result={mm} /> : null}
            </p>
          );
        })}
        {partial && partial.text ? (
          <p className="et-seg et-partial" aria-live="polite" data-partial-id={partial.partial_id}>
            {partial.text}
          </p>
        ) : null}
      </div>
      {labelRuns.map(({ a, r }) => (
        <span
          key={a.annotation_id}
          className="et-label"
          style={{ left: r.x, top: r.y - 4, borderColor: settings.palette === 'cvd' ? colorFor(a.primary, 'cvd') : a.color }}
        >
          <span aria-hidden="true">{GLYPH[a.primary]}</span> {LABEL_TEXT[a.primary]}
          {a.secondary && a.blend ? ` + ${LABEL_TEXT[a.blend.secondary].toLowerCase()}` : ''}
        </span>
      ))}
    </div>
  );
}
