import './visual.css';
import type { SettingsPanelProps, VisualSettings } from './contract';
import { CVD_COLORS, DEFAULT_COLORS, LABEL_TEXT } from './palette';
import { VISIBLE_CATEGORIES } from './contract';

/** Initial settings: reduced motion follows the OS preference. */
export function defaultSettings(): VisualSettings {
  let reduced = false;
  try {
    reduced = typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  } catch {
    /* ignore */
  }
  return { showLabels: false, palette: 'default', reducedMotion: reduced, mismatch: true };
}

export function SettingsPanel({ settings, onChange, mismatchAvailable = true }: SettingsPanelProps) {
  const set = <K extends keyof VisualSettings>(k: K, v: VisualSettings[K]) => onChange({ ...settings, [k]: v });
  const sw = settings.palette === 'cvd' ? CVD_COLORS : DEFAULT_COLORS;
  return (
    <section className="et-visual et-panel et-settings" aria-labelledby="et-settings-h">
      <header className="et-panel__head">
        <h2 id="et-settings-h">Display</h2>
      </header>
      <Toggle label="Emotion labels" hint="Show a small tag on each cloud" checked={settings.showLabels} onChange={(v) => set('showLabels', v)} />
      <Toggle label="Reduced motion" hint="Static clouds, no breathing" checked={settings.reducedMotion} onChange={(v) => set('reducedMotion', v)} />
      {mismatchAvailable ? (
        <Toggle
          label="Words vs voice"
          hint="Flag when wording and vocal cue differ"
          checked={settings.mismatch}
          onChange={(v) => set('mismatch', v)}
        />
      ) : null}
      <fieldset className="et-palette">
        <legend>Colors</legend>
        <label>
          <input type="radio" name="et-palette" checked={settings.palette === 'default'} onChange={() => set('palette', 'default')} /> Default
        </label>
        <label>
          <input type="radio" name="et-palette" checked={settings.palette === 'cvd'} onChange={() => set('palette', 'cvd')} /> Color-blind safe
        </label>
        <div className="et-swatches" aria-hidden="true">
          {VISIBLE_CATEGORIES.map((c) => (
            <span key={c} title={LABEL_TEXT[c]} style={{ background: sw[c] }} />
          ))}
        </div>
      </fieldset>
    </section>
  );
}

function Toggle({ label, hint, checked, onChange }: { label: string; hint: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="et-toggle">
      <span>
        <strong>{label}</strong>
        <small>{hint}</small>
      </span>
      <input type="checkbox" role="switch" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="et-toggle__track" aria-hidden="true" />
    </label>
  );
}
