import type { MismatchResult } from '../visual/contract';
import { mismatchTooltip } from './valence';

/** Small display-only badge. Tooltip works on hover and keyboard focus. */
export function MismatchBadge({ result }: { result: MismatchResult }) {
  const tip = mismatchTooltip(result);
  return (
    <span className="et-mismatch" tabIndex={0} role="note" aria-label={`Words and voice differ. ${tip}.`}>
      <span aria-hidden="true" className="et-mismatch__icon">
        {'⇄'}
      </span>
      Words and voice differ
      <span className="et-mismatch__tip" role="tooltip">
        {tip}
        <small>A gap between wording and vocal cue can mean many things, including model error. It does not mean sarcasm.</small>
      </span>
    </span>
  );
}
