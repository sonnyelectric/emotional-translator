/**
 * Standalone dev page: renders every visual component from hard-coded sample props,
 * no backend and no model download. Mount it from any entry:
 *   import Gallery from './visual/Gallery'; createRoot(el).render(<Gallery />)
 */
import { useMemo, useState } from 'react';
import './visual.css';
import { TranscriptView } from './TranscriptView';
import { EmotionProfile } from './EmotionProfile';
import { PhraseInspector } from './PhraseInspector';
import { SettingsPanel, defaultSettings } from './SettingsPanel';
import { SAMPLE_ANNOTATIONS, SAMPLE_MISMATCH, SAMPLE_PARTIAL, SAMPLE_SEGMENTS } from './gallerySample';
import type { AnnotationMap, VisualSettings } from './contract';

export default function Gallery() {
  const [settings, setSettings] = useState<VisualSettings>(defaultSettings);
  const [annotations, setAnnotations] = useState<AnnotationMap>(SAMPLE_ANNOTATIONS);
  const [selected, setSelected] = useState<string | null>('a-angry');
  const [width, setWidth] = useState(920);
  const sel = selected ? annotations[selected] ?? null : null;
  const phraseText = useMemo(() => {
    if (!sel) return undefined;
    const seg = SAMPLE_SEGMENTS.find((s) => s.segment_id === sel.segment_id);
    const ws = seg?.words ?? [];
    const a = ws.findIndex((w) => w.word_id === sel.start_word_id);
    const b = ws.findIndex((w) => w.word_id === sel.end_word_id);
    return ws.slice(a, b + 1).map((w) => w.text).join(' ');
  }, [sel]);

  const retract = () => {
    const { ['a-happy']: _gone, ...rest } = annotations;
    setAnnotations(rest);
  };

  return (
    <div className="et-visual et-gallery">
      <style>{`
        .et-gallery{min-height:100vh;background:radial-gradient(1200px 600px at 70% -10%,#1b2b4a 0,#101827 55%);padding:24px;box-sizing:border-box}
        .et-gallery h1{margin:0 0 4px;font-size:20px}
        .et-gallery p.sub{margin:0 0 18px;color:#93a3bd;font-size:13px}
        .et-gallery .grid{display:grid;grid-template-columns:340px minmax(0,1fr) 340px;gap:18px;align-items:start}
        .et-gallery .stack{display:grid;gap:18px}
        .et-gallery .bar{display:flex;gap:10px;margin-bottom:10px;flex-wrap:wrap}
        .et-gallery button.b{background:#192438;color:#eef2fa;border:1px solid rgba(160,190,230,.25);border-radius:8px;padding:6px 12px;font-size:12px;cursor:pointer}
        @media (max-width:1100px){.et-gallery .grid{grid-template-columns:1fr}}
      `}</style>
      <h1>Emotional Translator: visual gallery</h1>
      <p className="sub">Sample data adapted from shared/fixtures. Detected vocal cues, not feelings.</p>
      <div className="grid">
        <div className="stack">
          <EmotionProfile latest={sel ? sel.scores : null} settings={settings} />
        </div>
        <div className="et-panel" style={{ padding: 6 }}>
          <div className="bar" style={{ padding: '10px 14px 0' }}>
            <button className="b" onClick={() => setWidth((w) => (w === 920 ? 520 : 920))}>
              Toggle width ({width}px)
            </button>
            <button className="b" onClick={retract}>
              Retract happy cloud
            </button>
            <button className="b" onClick={() => setAnnotations(SAMPLE_ANNOTATIONS)}>
              Reset
            </button>
          </div>
          <div style={{ maxWidth: width, margin: '0 auto', transition: 'max-width .3s' }}>
            <TranscriptView
              segments={SAMPLE_SEGMENTS}
              partial={SAMPLE_PARTIAL}
              annotations={annotations}
              settings={settings}
              onInspect={setSelected}
              mismatch={SAMPLE_MISMATCH}
              selectedAnnotationId={selected}
            />
          </div>
        </div>
        <div className="stack">
          <SettingsPanel settings={settings} onChange={setSettings} />
          <PhraseInspector annotation={sel} onClose={() => setSelected(null)} phraseText={phraseText} mismatch={sel ? SAMPLE_MISMATCH.get(sel.segment_id) : null} />
        </div>
      </div>
    </div>
  );
}
