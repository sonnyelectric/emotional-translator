import { describe, expect, it } from 'vitest';
import type { Annotation, VisibleCategory } from '../visual/contract';
import { computeMismatch, dominantVoice, mismatchTooltip } from './valence';

function a(primary: VisibleCategory, over: Partial<Annotation> = {}): Annotation {
  return {
    annotation_id: 'a-' + primary,
    revision: 1,
    segment_id: 's',
    start_word_id: 's:w0',
    end_word_id: 's:w3',
    start_ms: 0,
    end_ms: 1000,
    state: 'finalized',
    primary,
    secondary: null,
    scores: {} as Annotation['scores'],
    support: 0.6,
    visual_intensity: 0.6,
    opacity: 0.5,
    shape: 'jagged',
    color: '#DC4545',
    blend: null,
    ...over,
  };
}
const pos = { label: 'POSITIVE', score: 0.99 };
const neg = { label: 'NEGATIVE', score: 0.97 };
const text = 'That is great thanks';

describe('computeMismatch', () => {
  it.each(['angry', 'sad', 'fearful', 'disgusted'] as const)('positive text + %s voice differs', (v) => {
    expect(computeMismatch('s', text, pos, [a(v)]).differs).toBe(true);
  });
  it.each(['happy', 'surprised'] as const)('negative text + %s voice differs', (v) => {
    expect(computeMismatch('s', text, neg, [a(v)]).differs).toBe(true);
  });
  it('matching valence does not differ', () => {
    expect(computeMismatch('s', text, pos, [a('happy')]).differs).toBe(false);
    expect(computeMismatch('s', text, neg, [a('angry')]).differs).toBe(false);
  });
  it('requires text score >= 0.9', () => {
    expect(computeMismatch('s', text, { label: 'POSITIVE', score: 0.89 }, [a('angry')]).differs).toBe(false);
    expect(computeMismatch('s', text, { label: 'POSITIVE', score: 0.9 }, [a('angry')]).differs).toBe(true);
  });
  it('requires a visible, non-faint annotation', () => {
    expect(computeMismatch('s', text, pos, []).differs).toBe(false);
    expect(computeMismatch('s', text, pos, [a('angry', { opacity: 0.2 })]).differs).toBe(false);
  });
  it('is false while sentiment is pending', () => {
    expect(computeMismatch('s', text, null, [a('angry')]).differs).toBe(false);
  });
  it('uses the time-weighted dominant voice', () => {
    const long = a('happy', { end_ms: 3000 });
    const short = a('angry', { end_ms: 500 });
    expect(dominantVoice([long, short])).toBe('happy');
    expect(computeMismatch('s', text, pos, [long, short]).differs).toBe(false);
  });
  it('tooltip wording', () => {
    expect(mismatchTooltip(computeMismatch('s', text, pos, [a('angry')]))).toBe(
      'Text reads positive; voice cue reads angry',
    );
  });
});
