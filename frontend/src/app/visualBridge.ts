// The ONE place the shell imports Builder BC2's visual components (PLAN section 5).
//
// The shell keeps its own reducer shapes (src/state): annotations are an ordered array of
// AnnotationView with `visible` and `state: 'draft' | 'final'`, and segments carry
// `words: Word[] | null`. BC2's contract (src/visual/contract.ts) wants an AnnotationMap
// with `state: 'draft' | 'finalized'` and `words?: TimedWord[]`. The adapters below convert
// at this boundary only; neither side changes its data, and nothing here alters scores.
import { createElement, useMemo } from 'react';
import {
  EmotionProfile,
  PhraseInspector as VisualPhraseInspector,
  SettingsPanel,
  TranscriptView as VisualTranscriptView,
} from '../visual';
import type {
  Annotation,
  AnnotationMap,
  MismatchResult,
  Segment as VisualSegment,
  VisualSettings,
} from '../visual/contract';
import { useMismatchWithStatus, type MismatchStatus } from '../mismatch';
import type { AnnotationView } from '../state/selectors';
import type { Segment } from '../state/reducer';

export { EmotionProfile, SettingsPanel };
export { MismatchBadge } from '../mismatch';
export type { VisualSettings, MismatchResult, MismatchStatus, AnnotationView };

export const DEFAULT_VISUAL_SETTINGS: VisualSettings = {
  showLabels: false,
  palette: 'default',
  reducedMotion: false,
  mismatch: true,
};

/** Shell annotation -> contract annotation. */
export function toVisualAnnotation(a: AnnotationView): Annotation {
  const { visible: _visible, state, ...rest } = a;
  return { ...rest, state: state === 'final' ? 'finalized' : 'draft' } as Annotation;
}

/** Only visible (non-retracted) annotations are drawn; later entries replace earlier ones. */
export function toAnnotationMap(list: readonly AnnotationView[]): AnnotationMap {
  const out: AnnotationMap = {};
  for (const a of list) if (a.visible) out[a.annotation_id] = toVisualAnnotation(a);
  return out;
}

export function toVisualSegments(segments: readonly Segment[]): VisualSegment[] {
  return segments.map((s) => ({
    segment_id: s.segment_id,
    text: s.text,
    timing_state: s.timing_state,
    language_code: s.language_code,
    words: s.words ?? undefined,
  }));
}

export interface TranscriptViewProps {
  segments: readonly Segment[];
  partial: { partial_id: string; text: string } | null;
  annotations: readonly AnnotationView[];
  settings: VisualSettings;
  onInspect: (annotationId: string) => void;
  mismatch?: ReadonlyMap<string, MismatchResult>;
  selectedAnnotationId?: string | null;
}

export function TranscriptView(p: TranscriptViewProps) {
  const segments = useMemo(() => toVisualSegments(p.segments), [p.segments]);
  const annotations = useMemo(() => toAnnotationMap(p.annotations), [p.annotations]);
  return createElement(VisualTranscriptView, {
    segments,
    partial: p.partial,
    annotations,
    settings: p.settings,
    onInspect: p.onInspect,
    mismatch: p.mismatch as Map<string, MismatchResult> | undefined,
    selectedAnnotationId: p.selectedAnnotationId ?? null,
  });
}

export interface PhraseInspectorProps {
  annotation: AnnotationView | null;
  onClose: () => void;
  phraseText?: string;
  mismatch?: MismatchResult | null;
  palette?: VisualSettings['palette'];
}

export function PhraseInspector({ annotation, ...rest }: PhraseInspectorProps) {
  const a = useMemo(() => (annotation ? toVisualAnnotation(annotation) : null), [annotation]);
  return createElement(VisualPhraseInspector, { annotation: a, ...rest });
}

/** Words of the annotation's range, for the inspector header. */
export function phraseTextFor(a: AnnotationView | null, segments: readonly Segment[]): string | undefined {
  if (!a) return undefined;
  const seg = segments.find((s) => s.segment_id === a.segment_id);
  const words = seg?.words;
  if (!words) return undefined;
  const i = words.findIndex((w) => w.word_id === a.start_word_id);
  const j = words.findIndex((w) => w.word_id === a.end_word_id);
  if (i < 0 || j < i) return undefined;
  return words
    .slice(i, j + 1)
    .map((w) => w.text)
    .join(' ');
}

/**
 * Words-versus-voice results (display-only, D3). When `enabled` is false the worker is never
 * created, so the text model is not downloaded.
 */
export function useMismatch(
  segments: readonly Segment[],
  annotations: readonly AnnotationView[],
  enabled: boolean,
): { results: Map<string, MismatchResult>; status: MismatchStatus } {
  const segs = useMemo(() => toVisualSegments(segments), [segments]);
  const anns = useMemo(() => toAnnotationMap(annotations), [annotations]);
  return useMismatchWithStatus(segs, anns, enabled);
}
