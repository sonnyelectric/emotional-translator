/**
 * Visual props contract between BC1 (app shell) and BC2 (visuals).
 * Field names mirror shared/schemas/v1/common.schema.json exactly (snake_case on the wire).
 * Pure types and constants only: safe for both lanes.
 */

/** Categories that can be drawn as a cloud (schema: visibleCategory). */
export type VisibleCategory = 'angry' | 'disgusted' | 'fearful' | 'happy' | 'sad' | 'surprised';

/** All nine score keys (schema: scores). */
export type ScoreLabel = VisibleCategory | 'neutral' | 'other' | 'unknown';

export type ScoreMap = Record<ScoreLabel, number>;

export type CloudShape = 'jagged' | 'wavy' | 'trembling' | 'radial' | 'rounded' | 'burst';

/** Default-palette hex values permitted by the schema. */
export type CloudColor = '#DC4545' | '#68A876' | '#9975D8' | '#EDB94B' | '#478CD4' | '#EF9858';

export interface Blend {
  secondary: VisibleCategory;
  /** (0, 0.5] */
  weight: number;
}

/** transcript.timed word (schema: word). */
export interface TimedWord {
  word_id: string;
  text: string;
  start_ms: number;
  end_ms: number;
}

/**
 * A committed segment as held by the reducer.
 * `words` is absent until transcript.timed arrives (timing_state === 'pending');
 * the view then renders `text` plainly and no clouds attach.
 */
export interface Segment {
  segment_id: string;
  text: string;
  timing_state?: string;
  language_code?: string | null;
  words?: TimedWord[];
}

/** transcript.partial payload (provisional, muted). */
export interface PartialText {
  partial_id: string;
  text: string;
  language_code?: string | null;
}

/**
 * emotion.updated payload (schema: annotation) plus reducer-side `state`.
 * The wire only ever carries state 'draft'; the reducer sets 'finalized'
 * after emotion.finalized for the same annotation_id.
 */
export interface Annotation {
  annotation_id: string;
  revision: number;
  segment_id: string;
  start_word_id: string;
  end_word_id: string;
  start_ms: number;
  end_ms: number;
  state: 'draft' | 'finalized';
  primary: VisibleCategory;
  secondary: VisibleCategory | null;
  scores: ScoreMap;
  /** Relative model support in [0,1]; NOT calibrated confidence. */
  support: number;
  visual_intensity: number;
  opacity: number;
  shape: CloudShape;
  color: CloudColor;
  blend: Blend | null;
}

export type AnnotationMap = Record<string, Annotation>;

export type PaletteName = 'default' | 'cvd';

export interface VisualSettings {
  showLabels: boolean;
  palette: PaletteName;
  reducedMotion: boolean;
  mismatch: boolean;
}

export type Valence = 'positive' | 'negative';

/** One entry of useMismatch(). */
export interface MismatchResult {
  segment_id: string;
  /** Text polarity from the in-browser classifier, or null while pending/unavailable. */
  textSentiment: Valence | null;
  /** Classifier score in [0,1] for textSentiment. */
  score: number;
  /** Dominant visible vocal category used for the comparison, or null if none. */
  voice: VisibleCategory | null;
  differs: boolean;
}

export interface TranscriptViewProps {
  segments: Segment[];
  partial: PartialText | null;
  annotations: AnnotationMap;
  settings: VisualSettings;
  onInspect: (annotationId: string) => void;
  /** Optional: result of useMismatch(); badges render only when settings.mismatch is true. */
  mismatch?: Map<string, MismatchResult>;
  /** Optional: highlights the cloud currently shown in the inspector. */
  selectedAnnotationId?: string | null;
}

export interface EmotionProfileProps {
  latest: ScoreMap | null;
  settings: VisualSettings;
}

export interface PhraseInspectorProps {
  annotation: Annotation | null;
  onClose: () => void;
  /** Optional words of the phrase for the header. */
  phraseText?: string;
  /** Optional mismatch result for the annotation's segment. */
  mismatch?: MismatchResult | null;
  /** Palette for the header glyph (defaults to 'default'). */
  palette?: PaletteName;
  /** True for hand-written replay data: the text must not say a voice or model produced it. */
  synthetic?: boolean;
}

export interface SettingsPanelProps {
  settings: VisualSettings;
  onChange: (next: VisualSettings) => void;
  /** Hide the mismatch toggle when the model cannot load. */
  mismatchAvailable?: boolean;
}

export const VISIBLE_CATEGORIES: readonly VisibleCategory[] = [
  'angry',
  'disgusted',
  'fearful',
  'happy',
  'sad',
  'surprised',
];

export const ALL_LABELS: readonly ScoreLabel[] = [
  'angry',
  'disgusted',
  'fearful',
  'happy',
  'neutral',
  'other',
  'sad',
  'surprised',
  'unknown',
];
