// Collapsible, scrollable history of older committed sentences. Annotations (including
// finalized geometry) are passed through unchanged. Auto-scroll only follows new text when
// the reader is already at the bottom, so it never steals reading position or focus.
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { Segment } from '../state/reducer';
import { TranscriptView, type AnnotationView, type MismatchResult, type VisualSettings } from '../app/visualBridge';

interface Props {
  segments: readonly Segment[];
  annotations: readonly AnnotationView[];
  settings: VisualSettings;
  onInspect(id: string): void;
  mismatch?: ReadonlyMap<string, MismatchResult>;
}

export function TranscriptHistory({ segments, annotations, settings, onInspect, mismatch }: Props) {
  const [open, setOpen] = useState(false);
  const scroller = useRef<HTMLDivElement | null>(null);
  const pinned = useRef(true);

  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const onScroll = () => {
      pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
  }, [open]);

  useLayoutEffect(() => {
    const el = scroller.current;
    if (open && el && pinned.current) el.scrollTop = el.scrollHeight;
  }, [open, segments.length]);

  if (segments.length === 0) return null;
  return (
    <section className="history" aria-label="Transcript history" data-testid="history">
      <button
        type="button"
        className="history-toggle"
        aria-expanded={open}
        aria-controls="history-body"
        onClick={() => setOpen((o) => !o)}
        data-testid="history-toggle"
      >
        <span className={open ? 'chev open' : 'chev'} aria-hidden="true">
          ▸
        </span>
        History · {segments.length} earlier {segments.length === 1 ? 'segment' : 'segments'}
      </button>
      {open && (
        <div id="history-body" className="history-body" ref={scroller} tabIndex={0}>
          <TranscriptView
            segments={segments}
            partial={null}
            annotations={annotations}
            settings={settings}
            onInspect={onInspect}
            mismatch={mismatch}
          />
        </div>
      )}
    </section>
  );
}
