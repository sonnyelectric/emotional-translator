import type { ReplayFixtureEntry } from '../protocol/events';

/**
 * Replay provenance wording. Synthetic fixtures must never read as saved model output;
 * "Recorded live session" is used only for a real recording (provenance recorded_result).
 */
export const SYNTHETIC_LABEL = 'Synthetic example (hand-written, not model output)';
export const RECORDED_LABEL = 'Recorded live session';
const RECORDED_DETAIL_DEFAULT = 'text, timestamps, scores; no audio';

export function provenanceLabel(entry: ReplayFixtureEntry): string {
  if (entry.provenance !== 'recorded_result') return SYNTHETIC_LABEL;
  const detail = (entry.provenance_detail ?? '').replace(/^recorded live session\s*/i, '').replace(/^\((.*)\)$/, '$1');
  const date = entry.recorded_on ? `, ${entry.recorded_on}` : '';
  return `${RECORDED_LABEL}${date} (${detail || RECORDED_DETAIL_DEFAULT})`;
}

/** Footnote under the emotion profile. In replay it states provenance instead of the model claim. */
export function cueFootnote(mode: 'live' | 'replay', entry: ReplayFixtureEntry | null): string {
  if (mode === 'live') return "Detected vocal cues from the emotion2vec+ model, not a reading of anyone's feelings.";
  if (!entry) return 'Replay. See the banner for where these events came from.';
  if (entry.provenance === 'recorded_result') {
    return `${RECORDED_LABEL}: vocal cues the emotion2vec+ model detected during a real session, replayed as saved. Not a reading of anyone's feelings.`;
  }
  return `${SYNTHETIC_LABEL}. These cues were written by hand to test the interface; no voice or model produced them.`;
}
