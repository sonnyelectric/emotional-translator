/**
 * Words-versus-voice logic. Pure and display-only: nothing here may feed back into
 * emotion scores, clouds, radar or annotations (TDD rule).
 */
import type { Annotation, MismatchResult, Valence, VisibleCategory } from '../visual/contract';

export const TEXT_SCORE_MIN = 0.9;
/** Annotation opacity below this is a "faint" cloud (TDD faint range 0.14 to 0.30). */
export const VISIBLE_OPACITY_MIN = 0.31;
export const MIN_WORDS = 2;

export const VOICE_VALENCE: Record<VisibleCategory, Valence> = {
  happy: 'positive',
  surprised: 'positive',
  angry: 'negative',
  sad: 'negative',
  fearful: 'negative',
  disgusted: 'negative',
};

export interface TextSentiment {
  label: 'POSITIVE' | 'NEGATIVE' | string;
  score: number;
}

export function polarity(label: string): Valence | null {
  const l = label.toUpperCase();
  if (l === 'POSITIVE') return 'positive';
  if (l === 'NEGATIVE') return 'negative';
  return null;
}

/**
 * Time-weighted dominant visible category for a segment. Faint clouds are ignored.
 * Weight = duration * support. Returns null when no visible annotation exists.
 */
export function dominantVoice(annotations: readonly Annotation[]): VisibleCategory | null {
  const totals = new Map<VisibleCategory, number>();
  for (const a of annotations) {
    if (a.opacity < VISIBLE_OPACITY_MIN) continue;
    const dur = Math.max(1, a.end_ms - a.start_ms);
    totals.set(a.primary, (totals.get(a.primary) ?? 0) + dur * Math.max(0.01, a.support));
  }
  let best: VisibleCategory | null = null;
  let bestV = 0;
  for (const [k, v] of totals) {
    if (v > bestV || (v === bestV && best !== null && k < best)) {
      best = k;
      bestV = v;
    }
  }
  return best;
}

export function opposes(text: Valence, voice: VisibleCategory): boolean {
  return VOICE_VALENCE[voice] !== text;
}

export function wordCount(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

export function computeMismatch(
  segmentId: string,
  text: string,
  sentiment: TextSentiment | null | undefined,
  annotations: readonly Annotation[],
): MismatchResult {
  const pol = sentiment ? polarity(sentiment.label) : null;
  const voice = dominantVoice(annotations);
  const score = sentiment ? sentiment.score : 0;
  const differs =
    pol !== null &&
    score >= TEXT_SCORE_MIN &&
    voice !== null &&
    wordCount(text) >= MIN_WORDS &&
    opposes(pol, voice);
  return { segment_id: segmentId, textSentiment: pol, score, voice, differs };
}

export function mismatchTooltip(r: MismatchResult): string {
  return `Text reads ${r.textSentiment ?? 'unclear'}; voice cue reads ${r.voice ?? 'unclear'}`;
}
