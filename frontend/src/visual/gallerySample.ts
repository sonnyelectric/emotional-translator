/** Hard-coded sample props for Gallery.tsx, adapted from shared/fixtures (replay_mixed, replay_anger_sad). */
import type { Annotation, AnnotationMap, MismatchResult, PartialText, ScoreMap, Segment, TimedWord } from './contract';

function words(seg: string, text: string, start = 100): TimedWord[] {
  let t = start;
  return text.split(' ').map((w, i) => {
    const out = { word_id: `${seg}:w${i}`, text: w, start_ms: t, end_ms: t + 330 };
    t += 360;
    return out;
  });
}

const T1 = 'I waited outside for almost an hour.';
const T2 = 'I was furious you did not call.';
const T3 = 'When I got home, I just felt alone.';
const T4 = 'That is great, thanks so much for cancelling on me again.';
const T5 = 'I cannot believe how this ended, after everything we built together over the years.';
const T6 = 'Wait, you did what?';
const T7 = 'I am not sure I should be here.';
const T8 = 'That smells absolutely awful.';
const T9 = 'We won, I am so happy right now!';

export const SAMPLE_SEGMENTS: Segment[] = [
  ['seg-1', T1],
  ['seg-2', T2],
  ['seg-3', T3],
  ['seg-4', T4],
  ['seg-5', T5],
  ['seg-6', T6],
  ['seg-7', T7],
  ['seg-8', T8],
  ['seg-9', T9],
].map(([id, text]) => ({ segment_id: id, text, timing_state: 'timed', words: words(id, text) }));

const z: ScoreMap = { angry: 0.02, disgusted: 0.02, fearful: 0.02, happy: 0.02, neutral: 0.05, other: 0.02, sad: 0.02, surprised: 0.02, unknown: 0.01 };

function ann(
  id: string,
  seg: string,
  a: number,
  b: number,
  primary: Annotation['primary'],
  scores: Partial<ScoreMap>,
  extra: Partial<Annotation> = {},
): Annotation {
  const shape = { angry: 'jagged', disgusted: 'wavy', fearful: 'trembling', happy: 'radial', sad: 'rounded', surprised: 'burst' } as const;
  const color = { angry: '#DC4545', disgusted: '#68A876', fearful: '#9975D8', happy: '#EDB94B', sad: '#478CD4', surprised: '#EF9858' } as const;
  const s = { ...z, ...scores };
  const w = SAMPLE_SEGMENTS.find((x) => x.segment_id === seg)!.words!;
  return {
    annotation_id: id,
    revision: 2,
    segment_id: seg,
    start_word_id: w[a].word_id,
    end_word_id: w[b].word_id,
    start_ms: w[a].start_ms,
    end_ms: w[b].end_ms,
    state: 'finalized',
    primary,
    secondary: null,
    scores: s,
    support: s[primary],
    visual_intensity: 0.7,
    opacity: 0.55,
    shape: shape[primary],
    color: color[primary],
    blend: null,
    ...extra,
  };
}

const list: Annotation[] = [
  ann('a-angry', 'seg-2', 2, 6, 'angry', { angry: 0.71, neutral: 0.1 }, { visual_intensity: 0.85, opacity: 0.6 }),
  ann('a-sad', 'seg-3', 4, 7, 'sad', { sad: 0.66, neutral: 0.09 }, { visual_intensity: 0.63, opacity: 0.55 }),
  ann('a-mm', 'seg-4', 3, 10, 'angry', { angry: 0.58, sad: 0.12, neutral: 0.14 }, { opacity: 0.5 }),
  ann('a-mixed', 'seg-5', 0, 13, 'angry', { angry: 0.46, sad: 0.35, neutral: 0.06 }, {
    state: 'draft',
    secondary: 'sad',
    blend: { secondary: 'sad', weight: 0.4321 },
    visual_intensity: 0.48,
    opacity: 0.45,
  }),
  ann('a-surp', 'seg-6', 0, 3, 'surprised', { surprised: 0.6, fearful: 0.1 }, { visual_intensity: 0.8 }),
  ann('a-fear', 'seg-7', 3, 7, 'fearful', { fearful: 0.55, sad: 0.2 }, { state: 'draft', opacity: 0.45 }),
  ann('a-disg', 'seg-8', 2, 3, 'disgusted', { disgusted: 0.62 }),
  ann('a-happy', 'seg-9', 0, 7, 'happy', { happy: 0.74, neutral: 0.08 }, { visual_intensity: 0.9, opacity: 0.6 }),
];

export const SAMPLE_ANNOTATIONS: AnnotationMap = Object.fromEntries(list.map((a) => [a.annotation_id, a]));

export const SAMPLE_PARTIAL: PartialText = { partial_id: 'p-1', text: 'and then she said that' };

export const SAMPLE_MISMATCH = new Map<string, MismatchResult>([
  ['seg-4', { segment_id: 'seg-4', textSentiment: 'positive', score: 0.99, voice: 'angry', differs: true }],
]);
