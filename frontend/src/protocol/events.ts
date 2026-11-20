// Checked-equivalent TypeScript types for shared/schemas/v1 (protocol v1.0).
// tests/contracts.test.ts keeps these aligned with the JSON Schemas by validating
// every shared fixture against both.

export const SCHEMA_VERSION = '1.0' as const;

export const SCORE_LABELS = [
  'angry',
  'disgusted',
  'fearful',
  'happy',
  'neutral',
  'other',
  'sad',
  'surprised',
  'unknown',
] as const;
export type ScoreLabel = (typeof SCORE_LABELS)[number];
export type ScoreMap = Record<ScoreLabel, number>;

export const VISIBLE_CATEGORIES = ['angry', 'disgusted', 'fearful', 'happy', 'sad', 'surprised'] as const;
export type VisibleCategory = (typeof VISIBLE_CATEGORIES)[number];

export type CloudShape = 'jagged' | 'wavy' | 'trembling' | 'radial' | 'rounded' | 'burst';
export type CloudColor = '#DC4545' | '#68A876' | '#9975D8' | '#EDB94B' | '#478CD4' | '#EF9858';

export const CATEGORY_TOKENS: Record<VisibleCategory, { shape: CloudShape; color: CloudColor }> = {
  angry: { shape: 'jagged', color: '#DC4545' },
  sad: { shape: 'rounded', color: '#478CD4' },
  happy: { shape: 'radial', color: '#EDB94B' },
  fearful: { shape: 'trembling', color: '#9975D8' },
  surprised: { shape: 'burst', color: '#EF9858' },
  disgusted: { shape: 'wavy', color: '#68A876' },
};

export type SessionState = 'idle' | 'connecting' | 'listening' | 'paused' | 'stopping' | 'stopped' | 'error';
export type SessionMode = 'live' | 'replay';
export type ScribeState = 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'failed' | 'not_required';
export type EmotionModelState = 'loading' | 'ready' | 'degraded' | 'failed' | 'not_required';

export interface SessionStatusPayload {
  state: SessionState;
  mode: SessionMode;
  scribe: ScribeState;
  emotion_model: EmotionModelState;
  detail: string | null;
  /** Present only for live `listening`. */
  sample_rate_hz?: 16000;
  channels?: 1;
  sample_format?: 's16le';
}

export interface Word {
  word_id: string;
  text: string;
  start_ms: number;
  end_ms: number;
}

export interface Blend {
  secondary: VisibleCategory;
  /** Secondary color fraction in (0, 0.5]. */
  weight: number;
}

export interface AnnotationPayload {
  annotation_id: string;
  revision: number;
  segment_id: string;
  start_word_id: string;
  end_word_id: string;
  start_ms: number;
  end_ms: number;
  state: 'draft';
  primary: VisibleCategory;
  secondary: VisibleCategory | null;
  scores: ScoreMap;
  support: number;
  visual_intensity: number;
  opacity: number;
  shape: CloudShape;
  color: CloudColor;
  blend: Blend | null;
}

export interface AnnotationRevisionPayload {
  annotation_id: string;
  revision: number;
}

interface Envelope<T extends string, P> {
  schema_version: '1.0';
  type: T;
  session_id: string;
  seq: number;
  issued_at_ms: number;
  payload: P;
}

export type SessionStatusEvent = Envelope<'session.status', SessionStatusPayload>;
export type TranscriptPartialEvent = Envelope<
  'transcript.partial',
  { partial_id: string; text: string; language_code: string | null }
>;
export type TranscriptCommittedEvent = Envelope<
  'transcript.committed',
  { segment_id: string; text: string; timing_state: 'pending'; language_code: string | null }
>;
export type TranscriptTimedEvent = Envelope<
  'transcript.timed',
  { segment_id: string; language_code: string | null; words: Word[]; text?: string }
>;
export type EmotionUpdatedEvent = Envelope<'emotion.updated', AnnotationPayload>;
export type EmotionRetractedEvent = Envelope<'emotion.retracted', AnnotationRevisionPayload>;
export type EmotionFinalizedEvent = Envelope<'emotion.finalized', AnnotationRevisionPayload>;
export type AlignmentWarningEvent = Envelope<'alignment.warning', { segment_id: string; code: string; message: string }>;
export type SessionWarningEvent = Envelope<'session.warning', { code: string; message: string; recoverable: true }>;
export type SessionErrorEvent = Envelope<'session.error', { code: string; message: string; recoverable: false }>;
export type SessionResetEvent = Envelope<'session.reset', Record<string, never>>;

export type ServerEvent =
  | SessionStatusEvent
  | TranscriptPartialEvent
  | TranscriptCommittedEvent
  | TranscriptTimedEvent
  | EmotionUpdatedEvent
  | EmotionRetractedEvent
  | EmotionFinalizedEvent
  | AlignmentWarningEvent
  | SessionWarningEvent
  | SessionErrorEvent
  | SessionResetEvent;

export type ServerEventType = ServerEvent['type'];

export const KNOWN_EVENT_TYPES: ReadonlySet<string> = new Set<ServerEventType>([
  'session.status',
  'transcript.partial',
  'transcript.committed',
  'transcript.timed',
  'emotion.updated',
  'emotion.retracted',
  'emotion.finalized',
  'alignment.warning',
  'session.warning',
  'session.error',
  'session.reset',
]);

/** A well-formed v1 envelope whose type this client does not know. Ignored after seq bookkeeping. */
export interface UnknownEvent {
  schema_version: '1.0';
  type: string;
  session_id: string;
  seq: number;
  issued_at_ms: number;
  payload: Record<string, unknown>;
  __unknown: true;
}

export type InboundEvent = ServerEvent | UnknownEvent;

export function isUnknownEvent(e: InboundEvent): e is UnknownEvent {
  return (e as UnknownEvent).__unknown === true;
}

// ---- Browser -> backend commands ----

export type ClientCommand =
  | { schema_version: '1.0'; type: 'session.start'; payload: { mode: 'live' } }
  | { schema_version: '1.0'; type: 'session.pause'; payload: Record<string, never> }
  | { schema_version: '1.0'; type: 'session.resume'; payload: Record<string, never> }
  | { schema_version: '1.0'; type: 'session.stop'; payload: Record<string, never> }
  | { schema_version: '1.0'; type: 'session.reset'; payload: Record<string, never> };

export type ClientCommandType = ClientCommand['type'];

export function makeCommand(type: ClientCommandType): ClientCommand {
  if (type === 'session.start') return { schema_version: SCHEMA_VERSION, type, payload: { mode: 'live' } };
  return { schema_version: SCHEMA_VERSION, type, payload: {} } as ClientCommand;
}

// ---- Replay HTTP ----

export interface ReplayFixtureEntry {
  id: string;
  file: string;
  case_name: string;
  duration_ms: number;
  provenance: 'synthetic_example' | 'recorded_result';
}

export interface ReplayManifest {
  schema_version: '1.0';
  source: 'saved_result';
  default_fixture: string;
  fixtures: ReplayFixtureEntry[];
}

export interface HttpErrorBody {
  code: string;
  message: string;
}

// ---- PCM format (binary frames) ----
export const PCM_SAMPLE_RATE = 16000;
export const PCM_FRAME_SAMPLES = 640; // 40 ms
export const PCM_MIN_FRAME_SAMPLES = 320; // 20 ms
export const PCM_MAX_FRAME_SAMPLES = 1600; // 100 ms
