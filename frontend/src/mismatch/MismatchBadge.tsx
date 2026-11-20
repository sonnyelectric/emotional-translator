import type { MismatchResult } from '../visual/contract';
import { mismatchTooltip } from './valence';

/** Small display-only badge. Tooltip works on hover and keyboard focus. */
export function MismatchBadge({ result }: { result: MismatchResult }) {
  const tip = mismatchTooltip(result);
  return (
    <span className="et-mismatch" tabIndex={0} role="note" aria-label={`Possible sarcasm: words and voice differ. ${tip}.`}>
      <span aria-hidden="true" className="et-mismatch__icon">
        {'⇄'}
      </span>
      Possible sarcasm
      <span className="et-mismatch__tip" role="tooltip">
        {tip}
        <small>The wording and the vocal cue point in opposite directions, which often signals sarcasm. It can also be model error.</small>
      </span>
    </span>
  );
}
