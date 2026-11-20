/**
 * Pure geometry for clouds: line-run grouping and procedural silhouettes.
 * No DOM access. Everything is a deterministic function of its inputs
 * (seed + time), so shapes never jump on re-render and tests can pin them.
 */
import type { Blend, CloudShape, VisibleCategory } from './contract';

export interface Rect {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** One line-run of a phrase, in container-local coordinates. */
export interface Run {
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * Group raw client rects (from Range.getClientRects) into one run per visual line.
 * Rects whose vertical centres differ by less than half the smaller height share a line.
 * Rects narrower than 1px (zero-width artefacts) are dropped. Output is sorted top to bottom.
 */
export function lineRuns(rects: readonly Rect[], origin: { left: number; top: number }): Run[] {
  const usable = rects
    .filter((r) => r.width >= 1 && r.height >= 1)
    .map((r) => ({ x: r.left - origin.left, y: r.top - origin.top, w: r.width, h: r.height }))
    .sort((a, b) => a.y + a.h / 2 - (b.y + b.h / 2) || a.x - b.x);
  const runs: Run[] = [];
  for (const r of usable) {
    const last = runs[runs.length - 1];
    if (last) {
      const lastC = last.y + last.h / 2;
      const c = r.y + r.h / 2;
      if (Math.abs(c - lastC) < Math.min(last.h, r.h) / 2) {
        const x0 = Math.min(last.x, r.x);
        const y0 = Math.min(last.y, r.y);
        const x1 = Math.max(last.x + last.w, r.x + r.w);
        const y1 = Math.max(last.y + last.h, r.y + r.h);
        last.x = x0;
        last.y = y0;
        last.w = x1 - x0;
        last.h = y1 - y0;
        continue;
      }
    }
    runs.push({ ...r });
  }
  return runs.map((r) => ({ x: round1(r.x), y: round1(r.y), w: round1(r.w), h: round1(r.h) }));
}

const round1 = (n: number) => Math.round(n * 10) / 10;

/** Structural equality so measurement does not trigger needless state updates. */
export function sameRuns(a: readonly Run[] | undefined, b: readonly Run[] | undefined): boolean {
  if (a === b) return true;
  if (!a || !b || a.length !== b.length) return false;
  return a.every((r, i) => r.x === b[i].x && r.y === b[i].y && r.w === b[i].w && r.h === b[i].h);
}

// ---------------------------------------------------------------------------
// Silhouette parameter table
// ---------------------------------------------------------------------------

export interface ShapeStyle {
  /** Displacement amplitude as a fraction of run height. */
  amp: number;
  /** 0 = smooth lobes, 1 = straight-edged spikes. Values in between blend the profiles. */
  spike: number;
  /** Lobe wavelength as a multiple of run height (smaller = more lobes). */
  lobeLen: number;
  /** Irregularity of spike heights / lobe sizes, 0..1. */
  jitter: number;
  /** Extra sag at the bottom, fraction of height (negative lifts the top instead). */
  droop: number;
  /** Time multiplier for the idle breathing. */
  speed: number;
  /** Fast small tremble amplitude (fraction of height). */
  tremble: number;
  /** Asymmetric wave strength for the wavy outline. */
  wave: number;
  /** Stroke width in px. */
  stroke: number;
  /** Squeeze of the fill relative to the hull (thin trembling cloud). */
  inset: number;
}

export const SHAPE_STYLES: Record<CloudShape, ShapeStyle> = {
  // angry: long irregular spikes, straight edges, restless
  jagged: { amp: 0.22, spike: 1, lobeLen: 0.5, jitter: 0.6, droop: 0, speed: 1.4, tremble: 0.02, wave: 0, stroke: 1.2, inset: 0 },
  // sad: big soft lobes, sagging, slow
  rounded: { amp: 0.2, spike: 0, lobeLen: 2.1, jitter: 0.35, droop: 0.22, speed: 0.35, tremble: 0, wave: 0, stroke: 1.1, inset: 0 },
  // happy: bouncy round lobes, lifted, lively
  radial: { amp: 0.17, spike: 0, lobeLen: 1.35, jitter: 0.15, droop: -0.1, speed: 1.1, tremble: 0, wave: 0, stroke: 1.1, inset: 0 },
  // fearful: thin, narrow outline with a fast small tremble
  trembling: { amp: 0.05, spike: 0, lobeLen: 0.8, jitter: 0.5, droop: 0, speed: 2.6, tremble: 0.07, wave: 0, stroke: 1, inset: 0.04 },
  // surprised: short regular starburst
  burst: { amp: 0.22, spike: 1, lobeLen: 0.9, jitter: 0.06, droop: 0, speed: 0.9, tremble: 0, wave: 0, stroke: 1.2, inset: 0 },
  // disgusted: asymmetric slow wave
  wavy: { amp: 0.13, spike: 0, lobeLen: 3.2, jitter: 0.2, droop: 0.05, speed: 0.6, tremble: 0, wave: 0.28, stroke: 1.1, inset: 0 },
};

export const CATEGORY_SHAPE: Record<VisibleCategory, CloudShape> = {
  angry: 'jagged',
  disgusted: 'wavy',
  fearful: 'trembling',
  happy: 'radial',
  sad: 'rounded',
  surprised: 'burst',
};

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

/** Blend two silhouettes: numeric parameters interpolate; the primary wins path mode. */
export function blendStyles(primary: CloudShape, blend: { shape: CloudShape; weight: number } | null): ShapeStyle {
  const a = SHAPE_STYLES[primary];
  if (!blend) return a;
  const b = SHAPE_STYLES[blend.shape];
  const t = Math.max(0, Math.min(0.5, blend.weight));
  const out = {} as ShapeStyle;
  for (const k of Object.keys(a) as (keyof ShapeStyle)[]) out[k] = lerp(a[k], b[k], t);
  return out;
}

export function shapeForBlend(secondary: VisibleCategory | null | undefined, blend: Blend | null): { shape: CloudShape; weight: number } | null {
  if (!blend) return null;
  return { shape: CATEGORY_SHAPE[blend.secondary ?? secondary ?? 'sad'], weight: blend.weight };
}

// ---------------------------------------------------------------------------
// Deterministic randomness
// ---------------------------------------------------------------------------

export function hashSeed(text: string): number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h >>> 0;
}

/** mulberry32: tiny seeded PRNG returning [0,1). */
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ---------------------------------------------------------------------------
// Blob generation
// ---------------------------------------------------------------------------

export type Pt = [number, number];

export interface BlobOptions {
  seed: number;
  /** Seconds. Pass 0 for a static shape. */
  t: number;
  /** visual_intensity in [0,1]; size multiplier is 1 + 0.25 * intensity. */
  intensity: number;
  /** Horizontal padding in px around the text. */
  padX?: number;
  padY?: number;
}

const HULL_POWER = 3.2; // superellipse exponent: pill-like hull that covers text corners
/**
 * Outline displacement is flattened vertically so spikes and lobes grow sideways and
 * mostly stay out of the neighbouring lines; horizontal ends keep the full silhouette.
 */
const VERTICAL_DISP = 0.6;

/** Number of outline points for a run (even, bounded). */
export function pointCount(w: number, h: number): number {
  const perimeter = 2 * (w + h);
  const n = Math.round(perimeter / Math.max(8, h * 0.45));
  const even = n % 2 === 0 ? n : n + 1;
  return Math.max(20, Math.min(72, even));
}

const sgnPow = (v: number, p: number) => Math.sign(v) * Math.pow(Math.abs(v), p);

/** Outline points for one line-run. Deterministic for identical inputs. */
export function blobPoints(run: Run, style: ShapeStyle, opts: BlobOptions): Pt[] {
  const { seed, t, intensity } = opts;
  const size = 1 + 0.25 * clamp01(intensity);
  // Generous padding: the hull clears every glyph, so displacement never cuts into text.
  const padX = opts.padX ?? Math.max(10, run.h * 0.5);
  const padY = opts.padY ?? Math.max(5, run.h * 0.2);
  const cx = run.x + run.w / 2;
  const cy = run.y + run.h / 2;
  const rx = ((run.w + 2 * padX) / 2) * (1 - style.inset * 0.3);
  const ry = ((run.h + 2 * padY) / 2) * (1 + (size - 1) * 0.5) * (1 - style.inset);
  const n = pointCount(run.w, run.h);
  const rand = rng(seed);
  const jit: number[] = [];
  const ph: number[] = [];
  for (let i = 0; i < n; i++) {
    jit.push(rand());
    ph.push(rand() * Math.PI * 2);
  }
  const phase0 = rand() * Math.PI * 2;
  const amp = style.amp * run.h * size;
  const perim = 2 * (run.w + run.h);
  const lobes = Math.max(3, Math.round(perim / (style.lobeLen * Math.max(run.h, 16))));
  const breathe = t * style.speed;
  const pts: Pt[] = [];
  for (let i = 0; i < n; i++) {
    const u = i / n;
    const a = u * Math.PI * 2;
    const c = Math.cos(a);
    const s = Math.sin(a);
    const x0 = rx * sgnPow(c, 2 / HULL_POWER);
    const y0 = ry * sgnPow(s, 2 / HULL_POWER);
    // outward normal of the superellipse
    let nx = sgnPow(c, HULL_POWER - 1) / rx;
    let ny = sgnPow(s, HULL_POWER - 1) / ry;
    const nl = Math.hypot(nx, ny) || 1;
    nx /= nl;
    ny /= nl;

    // spike profile: alternating long/short, irregular by jitter
    const long = i % 2 === 1;
    // valleys sit on the padded hull (never inside it), so spikes do not bite into glyphs
    const spikeH = long ? 0.55 + 0.45 * (1 - style.jitter * jit[i]) : 0.04 * jit[i];
    const spikeBreath = 1 + 0.12 * Math.sin(breathe * 1.7 + ph[i]);
    const spike = spikeH * spikeBreath;

    // lobe profile: smooth scallops around the perimeter, breathing slowly
    const lobePhase = u * Math.PI * 2 * lobes + phase0 + breathe * 0.9;
    const lobeSize = 1 + style.jitter * (jit[(i * 7) % n] - 0.5);
    const lobe = (Math.sin(lobePhase) * 0.5 + 0.4) * lobeSize;

    let d = style.spike * spike + (1 - style.spike) * lobe;
    // asymmetric wave (disgusted): low-frequency sway, different top and bottom
    d += style.wave * Math.sin(u * Math.PI * 2 * 2 + phase0 + breathe) * (c > 0 ? 1.2 : 0.7);
    // tremble: fast small per-point jitter
    d += style.tremble * 2 * Math.sin(t * 9 * Math.max(style.speed, 1) + ph[i] * 3) * (0.5 + jit[i]);
    const disp = d * amp;

    let x = cx + x0 + nx * disp;
    let y = cy + y0 + ny * disp * VERTICAL_DISP;
    // droop: sag the lower half, lift for negative values
    const lowerWeight = Math.max(0, s);
    y += style.droop * run.h * lowerWeight * (0.6 + 0.4 * Math.sin(breathe * 0.7 + phase0));
    if (style.droop < 0) y += style.droop * run.h * Math.max(0, -s) * 0.6;
    pts.push([x, y]);
  }
  return pts;
}

const f = (n: number) => (Math.round(n * 10) / 10).toString();

/** Straight-edged closed polygon path (angry, surprised). */
export function polygonPath(pts: readonly Pt[]): string {
  if (!pts.length) return '';
  return `M${f(pts[0][0])} ${f(pts[0][1])}` + pts.slice(1).map((p) => `L${f(p[0])} ${f(p[1])}`).join('') + 'Z';
}

/** Smooth closed Catmull-Rom spline converted to cubic Beziers. */
export function smoothPath(pts: readonly Pt[], tension = 1 / 6): string {
  const n = pts.length;
  if (n < 3) return polygonPath(pts);
  let d = `M${f(pts[0][0])} ${f(pts[0][1])}`;
  for (let i = 0; i < n; i++) {
    const p0 = pts[(i - 1 + n) % n];
    const p1 = pts[i];
    const p2 = pts[(i + 1) % n];
    const p3 = pts[(i + 2) % n];
    const c1x = p1[0] + (p2[0] - p0[0]) * tension;
    const c1y = p1[1] + (p2[1] - p0[1]) * tension;
    const c2x = p2[0] - (p3[0] - p1[0]) * tension;
    const c2y = p2[1] - (p3[1] - p1[1]) * tension;
    d += `C${f(c1x)} ${f(c1y)} ${f(c2x)} ${f(c2y)} ${f(p2[0])} ${f(p2[1])}`;
  }
  return d + 'Z';
}

/** Full path string for one run. Spiky styles are drawn straight, the rest smooth. */
export function blobPath(run: Run, style: ShapeStyle, opts: BlobOptions): string {
  const pts = blobPoints(run, style, opts);
  return style.spike >= 0.5 ? polygonPath(pts) : smoothPath(pts);
}

/**
 * Extend every run except the last toward the next line so adjacent per-line clouds overlap
 * and read as one coordinated shape. Pure; returns new runs.
 */
export function coordinateRuns(runs: readonly Run[], reach = 8): Run[] {
  return runs.map((r, i) => (i < runs.length - 1 ? { ...r, h: r.h + reach / 2 } : { ...r }));
}

export const clamp01 = (n: number) => Math.max(0, Math.min(1, n));
