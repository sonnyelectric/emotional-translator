import { useEffect, useRef, useState } from 'react';
import './visual.css';
import type { EmotionProfileProps, ScoreMap, VisibleCategory } from './contract';
import { colorFor, GLYPH, LABEL_TEXT } from './palette';

/** Axis order groups valence so the polygon silhouette is interpretable: positive on top. */
export const RADAR_AXES: readonly VisibleCategory[] = ['happy', 'surprised', 'fearful', 'sad', 'angry', 'disgusted'];

const SIZE = 280;
const C = SIZE / 2;
const R = 88;

export function radarPoint(i: number, k: number, value: number, radius = R): [number, number] {
  const a = -Math.PI / 2 + (2 * Math.PI * i) / k;
  return [C + radius * value * Math.cos(a), C + radius * value * Math.sin(a)];
}

/** Eases displayed values toward target; snaps under reduced motion. */
function useEased(target: number[], reduced: boolean): number[] {
  const [v, setV] = useState(target);
  const cur = useRef(target);
  useEffect(() => {
    if (reduced) {
      cur.current = target;
      setV(target);
      return;
    }
    let raf = 0;
    let last = performance.now();
    const step = (now: number) => {
      const k = 1 - Math.exp(-(now - last) / 1000 / 0.15);
      last = now;
      cur.current = cur.current.map((c, i) => c + (target[i] - c) * k);
      const done = cur.current.every((c, i) => Math.abs(target[i] - c) <= 0.002);
      setV([...cur.current]);
      if (!done) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target.join(','), reduced]);
  return v;
}

export function EmotionProfile({ latest, settings }: EmotionProfileProps) {
  const k = RADAR_AXES.length;
  const target = RADAR_AXES.map((c) => (latest ? clamp(latest[c]) : 0));
  const shown = useEased(target, settings.reducedMotion);
  const pts = shown.map((v, i) => radarPoint(i, k, v));
  const poly = pts.map((p) => p.map((n) => n.toFixed(1)).join(',')).join(' ');
  const rings = [0.25, 0.5, 0.75, 1];

  const sorted = latest
    ? [...RADAR_AXES].sort((a, b) => latest[b] - latest[a])
    : [...RADAR_AXES];
  const top = sorted.slice(0, 3).map((c) => `${LABEL_TEXT[c]} ${pct(latest![c])}`);
  const lead = latest ? leader(latest) : null;
  const accent = lead ? colorFor(lead, settings.palette) : '#5fd4e6';

  return (
    <section className="et-visual et-panel et-profile" aria-labelledby="et-profile-h">
      <header className="et-panel__head">
        <h2 id="et-profile-h">Emotion profile</h2>
        <span className="et-pill">{latest ? 'Latest phrase' : 'Waiting'}</span>
      </header>
      <svg
        className="et-radar"
        viewBox={`-40 0 ${SIZE + 80} ${SIZE}`}
        role="img"
        aria-label={
          latest ? `Relative model support by vocal cue. Highest: ${top.join(', ')}.` : 'Relative model support radar, no data yet.'
        }
      >
        <defs>
          <radialGradient id="et-radar-fill" cx="50%" cy="50%" r="50%">
            <stop offset="0" stopColor={accent} stopOpacity="0.15" />
            <stop offset="1" stopColor={accent} stopOpacity="0.5" />
          </radialGradient>
        </defs>
        {rings.map((r) => (
          <polygon
            key={r}
            className="et-radar__ring"
            points={RADAR_AXES.map((_, i) => radarPoint(i, k, r).map((n) => n.toFixed(1)).join(',')).join(' ')}
          />
        ))}
        {RADAR_AXES.map((_, i) => {
          const [x, y] = radarPoint(i, k, 1);
          return <line key={i} className="et-radar__axis" x1={C} y1={C} x2={x} y2={y} />;
        })}
        {latest ? <polygon className="et-radar__data" points={poly} fill="url(#et-radar-fill)" stroke={accent} /> : null}
        {RADAR_AXES.map((c, i) => {
          const [lx, ly] = radarPoint(i, k, 1, R + 22);
          const [vx, vy] = pts[i];
          const anchor = Math.abs(lx - C) < 6 ? 'middle' : lx > C ? 'start' : 'end';
          return (
            <g key={c}>
              {latest ? <circle cx={vx} cy={vy} r={4} fill={colorFor(c, settings.palette)} stroke="#0b1220" strokeWidth="1.5" /> : null}
              <text className="et-radar__label" x={lx} y={ly} textAnchor={anchor} dominantBaseline="middle">
                <tspan fill={colorFor(c, settings.palette)}>{GLYPH[c]}</tspan> {LABEL_TEXT[c]}
              </text>
            </g>
          );
        })}
      </svg>

      <div className="et-mix">
        <h3>Current mix</h3>
        <p className="et-mix__sub">Relative model support, not confidence</p>
        <ul>
          {sorted.map((c) => {
            const v = latest ? clamp(latest[c]) : 0;
            return (
              <li key={c}>
                <span className="et-mix__name">
                  <span aria-hidden="true" style={{ color: colorFor(c, settings.palette) }}>
                    {GLYPH[c]}
                  </span>{' '}
                  {LABEL_TEXT[c]}
                </span>
                <span className="et-mix__bar" aria-hidden="true">
                  <span style={{ width: `${(v * 100).toFixed(1)}%`, background: colorFor(c, settings.palette) }} />
                </span>
                <span className="et-mix__pct">{latest ? pct(v) : '--'}</span>
              </li>
            );
          })}
        </ul>
        {latest ? (
          <p className="et-mix__neutral">
            Neutral {pct(latest.neutral)} · other {pct(latest.other + latest.unknown)}
          </p>
        ) : null}
      </div>
    </section>
  );
}

const clamp = (n: number) => (Number.isFinite(n) ? Math.max(0, Math.min(1, n)) : 0);
const pct = (n: number) => `${Math.round(clamp(n) * 100)}%`;

function leader(s: ScoreMap): VisibleCategory {
  return RADAR_AXES.reduce((a, b) => (s[b] > s[a] ? b : a), RADAR_AXES[0]);
}
