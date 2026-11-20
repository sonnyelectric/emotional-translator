import { describe, expect, it } from 'vitest';
import type { ReplayFixtureEntry } from '../protocol/events';
import { cueFootnote, provenanceLabel } from './provenance';

const synthetic: ReplayFixtureEntry = {
  id: 'replay_demo',
  file: 'replay_demo.jsonl',
  case_name: 'Demo',
  duration_ms: 1000,
  provenance: 'synthetic_example',
};
const recorded: ReplayFixtureEntry = {
  id: 'replay_live_recorded',
  file: 'replay_live_recorded.jsonl',
  case_name: 'Recorded live session, 2026-11-20',
  duration_ms: 1000,
  provenance: 'recorded_result',
  provenance_detail: 'recorded live session (text, timestamps, scores; no audio)',
  recorded_on: '2026-11-20',
};

describe('replay provenance wording', () => {
  it('labels synthetic fixtures as hand-written, never as saved or model output', () => {
    const label = provenanceLabel(synthetic);
    expect(label).toBe('Synthetic example (hand-written, not model output)');
    const foot = cueFootnote('replay', synthetic);
    for (const s of [label, foot]) {
      expect(s).not.toMatch(/saved result/i);
      expect(s).not.toMatch(/from the emotion2vec/i);
      expect(s).not.toMatch(/recorded/i);
    }
  });
  it('labels a real recording as a recorded live session with date and detail', () => {
    expect(provenanceLabel(recorded)).toBe('Recorded live session, 2026-11-20 (text, timestamps, scores; no audio)');
    expect(cueFootnote('replay', recorded)).toMatch(/^Recorded live session: /);
  });
  it('keeps the model footnote for live mode only', () => {
    expect(cueFootnote('live', null)).toMatch(/emotion2vec\+ model/);
    expect(cueFootnote('replay', null)).not.toMatch(/emotion2vec/);
  });
});
