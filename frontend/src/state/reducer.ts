// One reducer for live WebSocket and replay events (TDD 7.4).
// It is pure: `applyEvent(state, event)` returns the next state plus an outcome so callers
// can distinguish applied, ignored (stale/other-session/unknown) and rejected events.
// Rejected events never mutate state.
import {
  CATEGORY_TOKENS,
  isUnknownEvent,
  type AnnotationPayload,
  type InboundEvent,
  type ServerEvent,
  type SessionStatusPayload,
  type Word,
} from '../protocol/events';

export interface Segment {
  segment_id: string;
  text: string;
  language_code: string | null;
  /** `pending` until `transcript.timed` arrives. */
  timing_state: 'pending' | 'timed';
  words: Word[] | null;
  committed_seq: number;
}

export interface AnnotationRecord {
  /** Latest visible geometry/scores (from the most recent accepted update). */
  payload: AnnotationPayload;
  revision: number;
  visible: boolean;
  final: boolean;
  updated_seq: number;
}

export interface Notice {
  seq: number;
  issued_at_ms: number;
  kind: 'session.warning' | 'alignment.warning';
  code: string;
  message: string;
  segment_id?: string;
}

export interface TranscriptState {
  sessionId: string | null;
  lastSeq: number;
  lastIssuedAt: number;
  /** True after the client sent `session.reset` on an open transport, until the ack. */
  awaitingResetAck: boolean;
  status: SessionStatusPayload | null;
  segments: Segment[];
  /** word_id -> segment_id, for anchor lookups and duplicate detection. */
  wordOwner: Record<string, string>;
  partial: { partial_id: string; text: string; language_code: string | null } | null;
  annotations: Record<string, AnnotationRecord>;
  /** Most recent accepted emotion.updated annotation id (for the profile panel). */
  latestAnnotationId: string | null;
  notices: Notice[];
  error: { code: string; message: string } | null;
  appliedCount: number;
}

export const initialState: TranscriptState = Object.freeze({
  sessionId: null,
  lastSeq: 0,
  lastIssuedAt: 0,
  awaitingResetAck: false,
  status: null,
  segments: [],
  wordOwner: {},
  partial: null,
  annotations: {},
  latestAnnotationId: null,
  notices: [],
  error: null,
  appliedCount: 0,
}) as TranscriptState;

export type Outcome =
  | { kind: 'applied' }
  | { kind: 'ignored'; reason: 'stale_seq' | 'other_session' | 'unbound' | 'unknown_type' }
  | { kind: 'rejected'; reason: string };

export interface ApplyResult {
  state: TranscriptState;
  outcome: Outcome;
}

const MAX_NOTICES = 50;
const SUPPORT_TOLERANCE = 1e-4;

function reject(state: TranscriptState, reason: string): ApplyResult {
  return { state, outcome: { kind: 'rejected', reason } };
}

function normalizeText(s: string): string {
  return s.normalize('NFC').replace(/\s+/g, ' ').trim();
}

/** Mark that a reset was requested on the open transport, so its ack may rebind the session. */
export function expectResetAck(state: TranscriptState): TranscriptState {
  return { ...state, awaitingResetAck: true };
}

/**
 * Forget the session binding (new transport or replay run) while keeping rendered content.
 * Content from a previous binding stays visible until explicit reset (PROTOCOL lifecycle).
 */
export function unbindTransport(state: TranscriptState): TranscriptState {
  return { ...state, sessionId: null, lastSeq: 0, lastIssuedAt: 0, awaitingResetAck: false };
}

export function applyEvent(state: TranscriptState, event: InboundEvent): ApplyResult {
  // --- session scope ---
  if (state.sessionId === null) {
    const bindsByStatus = event.type === 'session.status' && !isUnknownEvent(event);
    const bindsByReset = event.type === 'session.reset' && state.awaitingResetAck;
    if (!bindsByStatus && !bindsByReset) return { state, outcome: { kind: 'ignored', reason: 'unbound' } };
  } else if (event.session_id !== state.sessionId) {
    if (event.type === 'session.reset' && state.awaitingResetAck && !isUnknownEvent(event)) {
      return applyReset(event);
    }
    return { state, outcome: { kind: 'ignored', reason: 'other_session' } };
  }

  if (state.sessionId !== null && event.seq <= state.lastSeq) {
    return { state, outcome: { kind: 'ignored', reason: 'stale_seq' } };
  }
  if (state.sessionId !== null && event.issued_at_ms < state.lastIssuedAt) {
    return reject(state, 'issued_at_ms decreased');
  }

  if (isUnknownEvent(event)) {
    return {
      state: { ...state, lastSeq: event.seq, lastIssuedAt: event.issued_at_ms },
      outcome: { kind: 'ignored', reason: 'unknown_type' },
    };
  }

  if (event.type === 'session.reset') {
    if (state.sessionId !== null && !state.awaitingResetAck) return reject(state, 'unsolicited session.reset');
    return applyReset(event);
  }

  const res = applyKnown(state, event);
  if (res.outcome.kind !== 'applied') return res;
  return {
    state: {
      ...res.state,
      sessionId: event.session_id,
      lastSeq: event.seq,
      lastIssuedAt: event.issued_at_ms,
      appliedCount: res.state.appliedCount + 1,
    },
    outcome: res.outcome,
  };
}

function applyReset(event: ServerEvent): ApplyResult {
  return {
    state: {
      ...initialState,
      sessionId: event.session_id,
      lastSeq: event.seq,
      lastIssuedAt: event.issued_at_ms,
      appliedCount: 1,
    },
    outcome: { kind: 'applied' },
  };
}

function ok(state: TranscriptState): ApplyResult {
  return { state, outcome: { kind: 'applied' } };
}

function applyKnown(state: TranscriptState, event: ServerEvent): ApplyResult {
  switch (event.type) {
    case 'session.status':
      return ok({ ...state, status: event.payload });

    case 'transcript.partial': {
      const p = event.payload;
      return ok({ ...state, partial: p.text === '' ? null : { ...p } });
    }

    case 'transcript.committed': {
      const p = event.payload;
      if (state.segments.some((s) => s.segment_id === p.segment_id)) return reject(state, `duplicate commit ${p.segment_id}`);
      const seg: Segment = {
        segment_id: p.segment_id,
        text: p.text,
        language_code: p.language_code,
        timing_state: 'pending',
        words: null,
        committed_seq: event.seq,
      };
      return ok({ ...state, segments: [...state.segments, seg], partial: null });
    }

    case 'transcript.timed': {
      const p = event.payload;
      const idx = state.segments.findIndex((s) => s.segment_id === p.segment_id);
      if (idx < 0) return reject(state, `timing for unknown segment ${p.segment_id}`);
      const seg = state.segments[idx];
      if (seg.timing_state === 'timed') return reject(state, `segment ${p.segment_id} already timed`);
      if (p.words.length === 0) return reject(state, 'empty word list');
      const seen = new Set<string>();
      let prev: Word | null = null;
      for (const w of p.words) {
        if (seen.has(w.word_id) || state.wordOwner[w.word_id] !== undefined) return reject(state, `duplicate word id ${w.word_id}`);
        seen.add(w.word_id);
        if (!(w.end_ms > w.start_ms)) return reject(state, `nonpositive word interval ${w.word_id}`);
        if (prev && (w.start_ms < prev.start_ms || w.end_ms < prev.end_ms)) return reject(state, `out-of-order word ${w.word_id}`);
        prev = w;
      }
      const joined = normalizeText(p.words.map((w) => w.text).join(' '));
      if (joined !== normalizeText(seg.text)) return reject(state, `timed text mismatch for ${p.segment_id}`);
      const wordOwner = { ...state.wordOwner };
      for (const w of p.words) wordOwner[w.word_id] = p.segment_id;
      const segments = state.segments.slice();
      segments[idx] = {
        ...seg,
        timing_state: 'timed',
        words: p.words.map((w) => ({ ...w })),
        language_code: p.language_code ?? seg.language_code,
      };
      // Leaves the newer partial alone.
      return ok({ ...state, segments, wordOwner });
    }

    case 'emotion.updated': {
      const a = event.payload;
      const why = checkAnnotation(state, a);
      if (why) return reject(state, why);
      const existing = state.annotations[a.annotation_id];
      if (existing) {
        if (existing.final) return reject(state, `update after finalize ${a.annotation_id}`);
        if (a.revision <= existing.revision) return reject(state, `stale revision ${a.annotation_id}@${a.revision}`);
        const e = existing.payload;
        if (e.segment_id !== a.segment_id || e.start_word_id !== a.start_word_id || e.end_word_id !== a.end_word_id) {
          return reject(state, `anchors changed for ${a.annotation_id}`);
        }
      }
      const rec: AnnotationRecord = {
        payload: { ...a },
        revision: a.revision,
        visible: true,
        final: false,
        updated_seq: event.seq,
      };
      return ok({
        ...state,
        annotations: { ...state.annotations, [a.annotation_id]: rec },
        latestAnnotationId: a.annotation_id,
      });
    }

    case 'emotion.retracted': {
      const p = event.payload;
      const existing = state.annotations[p.annotation_id];
      if (!existing) return reject(state, `retract unknown ${p.annotation_id}`);
      if (existing.final) return reject(state, `retract after finalize ${p.annotation_id}`);
      if (!existing.visible) return reject(state, `retract hidden ${p.annotation_id}`);
      if (p.revision <= existing.revision) return reject(state, `stale revision ${p.annotation_id}@${p.revision}`);
      return ok({
        ...state,
        annotations: { ...state.annotations, [p.annotation_id]: { ...existing, revision: p.revision, visible: false } },
      });
    }

    case 'emotion.finalized': {
      const p = event.payload;
      const existing = state.annotations[p.annotation_id];
      if (!existing) return reject(state, `finalize unknown ${p.annotation_id}`);
      if (existing.final) return reject(state, `already final ${p.annotation_id}`);
      if (p.revision <= existing.revision) return reject(state, `stale revision ${p.annotation_id}@${p.revision}`);
      return ok({
        ...state,
        annotations: { ...state.annotations, [p.annotation_id]: { ...existing, revision: p.revision, final: true } },
      });
    }

    case 'alignment.warning':
    case 'session.warning': {
      const p = event.payload;
      const notice: Notice = {
        seq: event.seq,
        issued_at_ms: event.issued_at_ms,
        kind: event.type,
        code: p.code,
        message: p.message,
        ...(event.type === 'alignment.warning' ? { segment_id: event.payload.segment_id } : {}),
      };
      return ok({ ...state, notices: [...state.notices, notice].slice(-MAX_NOTICES) });
    }

    case 'session.error':
      return ok({ ...state, error: { code: event.payload.code, message: event.payload.message } });

    default:
      return reject(state, 'unhandled type');
  }
}

/** Semantic checks for an annotation payload (PROTOCOL validation order step 3). */
function checkAnnotation(state: TranscriptState, a: AnnotationPayload): string | null {
  const seg = state.segments.find((s) => s.segment_id === a.segment_id);
  if (!seg) return `annotation ${a.annotation_id} references unknown segment`;
  if (!seg.words) return `annotation ${a.annotation_id} references untimed segment`;
  const si = seg.words.findIndex((w) => w.word_id === a.start_word_id);
  const ei = seg.words.findIndex((w) => w.word_id === a.end_word_id);
  if (si < 0 || ei < 0) return `annotation ${a.annotation_id} anchor word missing`;
  if (si > ei) return `annotation ${a.annotation_id} anchors reversed`;
  if (seg.words[si].start_ms !== a.start_ms || seg.words[ei].end_ms !== a.end_ms) {
    return `annotation ${a.annotation_id} interval differs from anchors`;
  }
  const tokens = CATEGORY_TOKENS[a.primary];
  if (!tokens || tokens.shape !== a.shape || tokens.color !== a.color) return `annotation ${a.annotation_id} token mismatch`;
  if (a.secondary === null) {
    if (a.blend !== null) return `annotation ${a.annotation_id} blend without secondary`;
  } else {
    if (a.secondary === a.primary) return `annotation ${a.annotation_id} secondary equals primary`;
    if (!a.blend || a.blend.secondary !== a.secondary) return `annotation ${a.annotation_id} blend disagrees with secondary`;
  }
  if (Math.abs(a.support - a.scores[a.primary]) > SUPPORT_TOLERANCE) return `annotation ${a.annotation_id} support mismatch`;
  return null;
}

/** Local reset (no transport): clear everything. */
export function resetLocal(): TranscriptState {
  return { ...initialState };
}
