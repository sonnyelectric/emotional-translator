// Read-only display selectors. They never mutate stored annotations or segments.
import type { AnnotationPayload, ScoreMap, Word } from '../protocol/events';
import type { Segment, TranscriptState } from './reducer';

/** Annotation as handed to visual components: latest payload plus lifecycle flags. */
export interface AnnotationView extends Omit<AnnotationPayload, 'state'> {
  state: 'draft' | 'final';
  /** False after `emotion.retracted`; a hidden final annotation never shows again. */
  visible: boolean;
}

export interface SentenceToken {
  segment_id: string;
  /** Present once timed; stable `data-word-id` anchor. */
  word_id: string | null;
  text: string;
}

export interface Sentence {
  /** Stable key: first token's segment + index. */
  key: string;
  tokens: SentenceToken[];
  segment_ids: string[];
  /** True if the sentence ends with terminal punctuation. */
  complete: boolean;
}

const TERMINAL = /[.!?…]["')\]]*$/;

function segmentTokens(seg: Segment): SentenceToken[] {
  if (seg.words) {
    return seg.words.map((w: Word) => ({ segment_id: seg.segment_id, word_id: w.word_id, text: w.text }));
  }
  return seg.text
    .split(/\s+/)
    .filter(Boolean)
    .map((t) => ({ segment_id: seg.segment_id, word_id: null, text: t }));
}

/**
 * Punctuation-aware sentence split across committed segments. One commit may produce
 * several sentences, and one sentence may span adjacent commits. Word IDs and segment
 * ownership are preserved on every token.
 */
export function selectSentences(segments: readonly Segment[]): Sentence[] {
  const out: Sentence[] = [];
  let cur: SentenceToken[] = [];
  const flush = (complete: boolean) => {
    if (cur.length === 0) return;
    const segIds: string[] = [];
    for (const t of cur) if (!segIds.includes(t.segment_id)) segIds.push(t.segment_id);
    const first = cur[0];
    out.push({ key: `${first.segment_id}#${first.word_id ?? first.text}#${out.length}`, tokens: cur, segment_ids: segIds, complete });
    cur = [];
  };
  for (const seg of segments) {
    for (const tok of segmentTokens(seg)) {
      cur.push(tok);
      if (TERMINAL.test(tok.text)) flush(true);
    }
  }
  flush(false);
  return out;
}

export interface CenterSplit {
  center: Segment[];
  history: Segment[];
}

/**
 * Pick the segments that hold the newest ~`maxSentences` sentences for the center view.
 * A segment that straddles the boundary stays whole in the center, so the visual
 * components always receive whole segments with their word IDs.
 */
export function selectCenterAndHistory(segments: readonly Segment[], maxSentences = 3): CenterSplit {
  if (segments.length === 0) return { center: [], history: [] };
  const sentences = selectSentences(segments);
  const keep = sentences.slice(-maxSentences);
  const firstSeg = keep.length > 0 ? keep[0].segment_ids[0] : segments[segments.length - 1].segment_id;
  const cut = segments.findIndex((s) => s.segment_id === firstSeg);
  const at = cut < 0 ? 0 : cut;
  return { center: segments.slice(at), history: segments.slice(0, at) };
}

export function selectAnnotations(state: TranscriptState): AnnotationView[] {
  return Object.values(state.annotations)
    .sort((a, b) => a.updated_seq - b.updated_seq)
    .map((r) => ({
      ...r.payload,
      revision: r.revision,
      state: r.final ? 'final' : 'draft',
      visible: r.visible,
    }));
}

export function selectAnnotationsForSegments(all: readonly AnnotationView[], segments: readonly Segment[]): AnnotationView[] {
  const ids = new Set(segments.map((s) => s.segment_id));
  return all.filter((a) => ids.has(a.segment_id));
}

/** Scores of the most recently updated, still-visible annotation (emotion profile panel). */
export function selectLatestScores(state: TranscriptState): ScoreMap | null {
  const id = state.latestAnnotationId;
  if (!id) return null;
  const rec = state.annotations[id];
  if (!rec || !rec.visible) return null;
  return rec.payload.scores;
}

export function selectAnnotation(state: TranscriptState, id: string | null): AnnotationView | null {
  if (!id) return null;
  const r = state.annotations[id];
  if (!r) return null;
  return { ...r.payload, revision: r.revision, state: r.final ? 'final' : 'draft', visible: r.visible };
}
