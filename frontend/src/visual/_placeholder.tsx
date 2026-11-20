// TEMPORARY stand-ins for Builder BC2's components (PLAN section 5 contract).
// Written by BC1 only so the shell compiles and stays usable before BC2's real
// TranscriptView / EmotionProfile / PhraseInspector / SettingsPanel / useMismatch land.
// The integrator swaps them in by editing src/app/visualBridge.ts; delete this file then.
// These render plain highlights (no SVG clouds) and never invent model output.
import { useMemo } from 'react';
import type { ScoreMap, VisibleCategory, Word } from '../protocol/events';
import { SCORE_LABELS, VISIBLE_CATEGORIES } from '../protocol/events';

// ---- contract-shaped types (BC2's contract.ts is authoritative once it exists) ----

export interface VisualSettings {
  showLabels: boolean;
  palette: 'default' | 'cvd';
  reducedMotion: boolean;
  mismatch: boolean;
}

export interface SegmentView {
  segment_id: string;
  text: string;
  timing_state: 'pending' | 'timed';
  words: Word[] | null;
  language_code: string | null;
}

export interface PartialView {
  partial_id: string;
  text: string;
}

export interface AnnotationView {
  annotation_id: string;
  revision: number;
  segment_id: string;
  start_word_id: string;
  end_word_id: string;
  start_ms: number;
  end_ms: number;
  state: 'draft' | 'final';
  visible: boolean;
  primary: VisibleCategory;
  secondary: VisibleCategory | null;
  scores: ScoreMap;
  support: number;
  visual_intensity: number;
  opacity: number;
  shape: string;
  color: string;
  blend: { secondary: VisibleCategory; weight: number } | null;
}

export interface MismatchResult {
  textSentiment: 'POSITIVE' | 'NEGATIVE' | 'unclear';
  score: number;
  voice: VisibleCategory | null;
  differs: boolean;
}

export interface TranscriptViewProps {
  segments: readonly SegmentView[];
  partial: PartialView | null;
  annotations: readonly AnnotationView[];
  settings: VisualSettings;
  onInspect: (annotationId: string) => void;
  mismatch?: ReadonlyMap<string, MismatchResult>;
}

const CVD: Record<VisibleCategory, string> = {
  angry: '#D55E00',
  sad: '#56B4E9',
  happy: '#F0E442',
  fearful: '#CC79A7',
  surprised: '#E69F00',
  disgusted: '#009E73',
};
const DEFAULT: Record<VisibleCategory, string> = {
  angry: '#DC4545',
  sad: '#478CD4',
  happy: '#EDB94B',
  fearful: '#9975D8',
  surprised: '#EF9858',
  disgusted: '#68A876',
};

function colorFor(c: VisibleCategory, palette: VisualSettings['palette']) {
  return (palette === 'cvd' ? CVD : DEFAULT)[c];
}

function hexA(hex: string, a: number) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a.toFixed(3)})`;
}

export function TranscriptView({ segments, partial, annotations, settings, onInspect }: TranscriptViewProps) {
  return (
    <div className="ph-transcript">
      {segments.map((seg) => (
        <PlaceholderSegment key={seg.segment_id} seg={seg} annotations={annotations} settings={settings} onInspect={onInspect} />
      ))}
      {partial && partial.text && (
        <span className="ph-partial" aria-live="off" data-partial-id={partial.partial_id}>
          {partial.text}
        </span>
      )}
    </div>
  );
}

function PlaceholderSegment({
  seg,
  annotations,
  settings,
  onInspect,
}: {
  seg: SegmentView;
  annotations: readonly AnnotationView[];
  settings: VisualSettings;
  onInspect: (id: string) => void;
}) {
  if (!seg.words) {
    return (
      <span className="ph-seg" data-segment-id={seg.segment_id} data-timing="pending">
        {seg.text}{' '}
      </span>
    );
  }
  const words = seg.words;
  const mine = annotations.filter((a) => a.segment_id === seg.segment_id && a.visible);
  const parts: (JSX.Element | string)[] = [];
  let i = 0;
  while (i < words.length) {
    const ann = mine.find((a) => a.start_word_id === words[i].word_id);
    if (ann) {
      const end = words.findIndex((w) => w.word_id === ann.end_word_id);
      const slice = words.slice(i, end + 1);
      const col = colorFor(ann.primary, settings.palette);
      parts.push(
        <span
          key={ann.annotation_id}
          className="ph-phrase"
          data-annotation-id={ann.annotation_id}
          data-primary={ann.primary}
          data-state={ann.state}
          role="button"
          tabIndex={0}
          aria-label={`${slice.map((w) => w.text).join(' ')}: detected vocal cue ${ann.primary}, support ${Math.round(ann.support * 100)} percent`}
          style={{ background: hexA(col, Math.min(0.6, ann.opacity)), boxShadow: `inset 0 -2px 0 ${col}` }}
          onClick={() => onInspect(ann.annotation_id)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              onInspect(ann.annotation_id);
            }
          }}
        >
          {slice.map((w, k) => (
            <span key={w.word_id} data-word-id={w.word_id}>
              {w.text}
              {k < slice.length - 1 ? ' ' : ''}
            </span>
          ))}
          {settings.showLabels && <span className="ph-label">{ann.primary}</span>}
        </span>,
        ' ',
      );
      i = end + 1;
    } else {
      parts.push(
        <span key={words[i].word_id} data-word-id={words[i].word_id}>
          {words[i].text}{' '}
        </span>,
      );
      i++;
    }
  }
  return (
    <span className="ph-seg" data-segment-id={seg.segment_id} data-timing="timed">
      {parts}
    </span>
  );
}

export function EmotionProfile({ latest, settings }: { latest: ScoreMap | null; settings: VisualSettings }) {
  if (!latest) return <p className="ph-empty">No analyzed phrase yet. Detected vocal cues appear here.</p>;
  return (
    <ul className="ph-mix" aria-label="Detected vocal cue mix for the latest analyzed phrase">
      {VISIBLE_CATEGORIES.map((c) => (
        <li key={c}>
          <span className="ph-mix-name">{c}</span>
          <span className="ph-mix-bar">
            <span style={{ width: `${Math.round(latest[c] * 100)}%`, background: colorFor(c, settings.palette) }} />
          </span>
          <span className="ph-mix-val">{Math.round(latest[c] * 100)}%</span>
        </li>
      ))}
    </ul>
  );
}

export function PhraseInspector({ annotation, onClose }: { annotation: AnnotationView | null; onClose: () => void }) {
  if (!annotation) return null;
  return (
    <div className="ph-inspector" role="dialog" aria-label="Phrase details">
      <button className="ph-close" onClick={onClose} aria-label="Close phrase details">
        ×
      </button>
      <h3>
        Detected vocal cue: {annotation.primary}
        {annotation.secondary ? ` + ${annotation.secondary}` : ''}
      </h3>
      <p>
        Approximate model support {Math.round(annotation.support * 100)}% · {annotation.state}
      </p>
      <table>
        <tbody>
          {SCORE_LABELS.map((l) => (
            <tr key={l}>
              <th scope="row">{l}</th>
              <td>{annotation.scores[l].toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="ph-caveat">Model estimate of vocal tone, not a statement about feelings. It can be wrong.</p>
    </div>
  );
}

export function SettingsPanel({ settings, onChange }: { settings: VisualSettings; onChange: (s: VisualSettings) => void }) {
  return (
    <fieldset className="ph-settings">
      <legend>Display</legend>
      <label>
        <input type="checkbox" checked={settings.showLabels} onChange={(e) => onChange({ ...settings, showLabels: e.target.checked })} />{' '}
        Always show emotion labels
      </label>
      <label>
        <input
          type="checkbox"
          checked={settings.palette === 'cvd'}
          onChange={(e) => onChange({ ...settings, palette: e.target.checked ? 'cvd' : 'default' })}
        />{' '}
        Color-blind-safe palette
      </label>
      <label>
        <input type="checkbox" checked={settings.reducedMotion} onChange={(e) => onChange({ ...settings, reducedMotion: e.target.checked })} />{' '}
        Reduce motion
      </label>
      <label>
        <input type="checkbox" checked={settings.mismatch} onChange={(e) => onChange({ ...settings, mismatch: e.target.checked })} /> Flag
        when words and voice differ
      </label>
    </fieldset>
  );
}

/** Placeholder: the real hook (BC2) runs text sentiment in a worker. Returns no flags. */
export function useMismatch(
  _segments: readonly SegmentView[],
  _annotations: readonly AnnotationView[],
): Map<string, MismatchResult> {
  return useMemo(() => new Map(), []);
}
