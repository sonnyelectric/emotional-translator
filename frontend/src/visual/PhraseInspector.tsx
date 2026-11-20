import { useEffect, useRef } from 'react';
import './visual.css';
import { ALL_LABELS, type PhraseInspectorProps } from './contract';
import { GLYPH, LABEL_TEXT, DEFAULT_COLORS } from './palette';
import { mismatchTooltip } from '../mismatch/valence';

const sec = (ms: number) => (ms / 1000).toFixed(2) + 's';

export function PhraseInspector({ annotation: a, onClose, phraseText, mismatch }: PhraseInspectorProps) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!a) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    ref.current?.focus();
    return () => window.removeEventListener('keydown', onKey);
  }, [a?.annotation_id, onClose]);

  if (!a) return null;
  const rows = [...ALL_LABELS].sort((x, y) => a.scores[y] - a.scores[x]);
  const blendText = a.blend ? ` with a secondary ${LABEL_TEXT[a.blend.secondary].toLowerCase()} cue (${Math.round(a.blend.weight * 100)}% blend)` : '';
  const explain =
    `The voice in this phrase scored highest for ${LABEL_TEXT[a.primary].toLowerCase()} (${Math.round(a.support * 100)}% relative model support)${blendText}. ` +
    `It marks a vocal cue across the phrase, not a single word, and not what anyone feels.`;

  return (
    <aside className="et-visual et-panel et-inspector" ref={ref} tabIndex={-1} aria-label="Phrase details">
      <header className="et-panel__head">
        <h2>
          <span aria-hidden="true" style={{ color: DEFAULT_COLORS[a.primary] }}>
            {GLYPH[a.primary]}
          </span>{' '}
          {LABEL_TEXT[a.primary]}
          {a.blend ? <span className="et-dim"> + {LABEL_TEXT[a.blend.secondary].toLowerCase()}</span> : null}
        </h2>
        <button type="button" className="et-x" onClick={onClose} aria-label="Close details">
          {'×'}
        </button>
      </header>
      {phraseText ? <blockquote className="et-inspector__quote">{'“'}{phraseText}{'”'}</blockquote> : null}
      <p className="et-inspector__explain">{explain}</p>
      <dl className="et-facts">
        <div>
          <dt>Relative support</dt>
          <dd>{Math.round(a.support * 100)}%</dd>
        </div>
        <div>
          <dt>State</dt>
          <dd>{a.state === 'finalized' ? 'Finalized' : 'Draft (may still change)'}</dd>
        </div>
        <div>
          <dt>Revision</dt>
          <dd>{a.revision}</dd>
        </div>
        <div>
          <dt>Time span</dt>
          <dd>
            {sec(a.start_ms)} to {sec(a.end_ms)}
          </dd>
        </div>
      </dl>
      <table className="et-scores">
        <caption>Model scores (not calibrated probabilities)</caption>
        <thead>
          <tr>
            <th scope="col">Label</th>
            <th scope="col">Score</th>
            <th scope="col" aria-hidden="true" />
          </tr>
        </thead>
        <tbody>
          {rows.map((l) => (
            <tr key={l} className={l === a.primary ? 'is-primary' : undefined}>
              <th scope="row">{LABEL_TEXT[l]}</th>
              <td>{(a.scores[l] * 100).toFixed(0)}%</td>
              <td aria-hidden="true">
                <span className="et-mix__bar">
                  <span style={{ width: `${a.scores[l] * 100}%` }} />
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {mismatch?.differs ? <p className="et-inspector__mm">Words and voice differ. {mismatchTooltip(mismatch)}.</p> : null}
    </aside>
  );
}
