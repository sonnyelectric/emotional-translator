/**
 * Imperative cloud renderer. One shared requestAnimationFrame loop writes every
 * path's `d` (no React state per frame). Targets arrive via sync(); display values
 * ease toward them (about 250-450 ms) so revisions morph instead of popping.
 */
import { blendStyles, blobPath, clamp01, coordinateRuns, hashSeed, type Run } from './geometry';
import type { CloudShape } from './contract';
import { hexToRgb, rgbToCss } from './palette';

export interface CloudSpec {
  id: string;
  runs: Run[];
  shape: CloudShape;
  blendShape: CloudShape | null;
  blendWeight: number;
  color: string;
  color2: string | null;
  /** annotation.opacity in [0,1]. */
  opacity: number;
  /** annotation.visual_intensity in [0,1]. */
  intensity: number;
  finalized: boolean;
  selected: boolean;
}

interface Live {
  spec: CloudSpec;
  seed: number;
  g: SVGGElement;
  grad: SVGLinearGradientElement;
  stops: SVGStopElement[];
  paths: SVGPathElement[];
  cur: { opacity: number; intensity: number; weight: number; c1: [number, number, number]; c2: [number, number, number] };
  leaving: boolean;
}

const SVGNS = 'http://www.w3.org/2000/svg';
const MAX_FILL = 0.62; // keeps off-white text readable on the lightest clouds
const DRAFT_FACTOR = 0.82; // draft is slightly fainter, finalized is settled

export class CloudEngine {
  private clouds = new Map<string, Live>();
  private raf = 0;
  private last = 0;
  private t0 = 0;
  private reduced = false;
  private defs: SVGDefsElement;
  private root: SVGGElement;
  private uid = Math.random().toString(36).slice(2, 7);

  constructor(private svg: SVGSVGElement) {
    this.defs = document.createElementNS(SVGNS, 'defs');
    this.root = document.createElementNS(SVGNS, 'g');
    svg.append(this.defs, this.root);
    document.addEventListener('visibilitychange', this.onVisibility);
  }

  setReducedMotion(v: boolean) {
    this.reduced = v;
    this.kick();
  }

  sync(specs: readonly CloudSpec[]) {
    const seen = new Set<string>();
    for (const spec of specs) {
      seen.add(spec.id);
      let live = this.clouds.get(spec.id);
      if (!live) live = this.create(spec);
      live.spec = spec;
      live.leaving = false;
      this.fitPaths(live);
    }
    for (const [id, live] of this.clouds) if (!seen.has(id)) live.leaving = true;
    this.kick();
  }

  destroy() {
    cancelAnimationFrame(this.raf);
    document.removeEventListener('visibilitychange', this.onVisibility);
    this.svg.replaceChildren();
    this.clouds.clear();
  }

  private onVisibility = () => {
    if (!document.hidden) this.kick();
  };

  private create(spec: CloudSpec): Live {
    const gid = `et-grad-${this.uid}-${hashSeed(spec.id).toString(36)}`;
    const grad = document.createElementNS(SVGNS, 'linearGradient');
    grad.setAttribute('id', gid);
    grad.setAttribute('x1', '0');
    grad.setAttribute('x2', '1');
    grad.setAttribute('y1', '0');
    grad.setAttribute('y2', '0');
    const stops = [0, 1, 2].map(() => document.createElementNS(SVGNS, 'stop'));
    grad.append(...stops);
    this.defs.append(grad);
    const g = document.createElementNS(SVGNS, 'g');
    g.setAttribute('data-annotation-id', spec.id);
    g.setAttribute('class', 'et-cloud');
    this.root.append(g);
    const c1 = hexToRgb(spec.color);
    const live: Live = {
      spec,
      seed: hashSeed(spec.id),
      g,
      grad,
      stops,
      paths: [],
      // new clouds fade in from zero; colour/geometry start at the target
      cur: { opacity: 0, intensity: spec.intensity, weight: spec.blendWeight, c1, c2: hexToRgb(spec.color2 ?? spec.color) },
      leaving: false,
    };
    live.cur.c1 = c1;
    this.clouds.set(spec.id, live);
    return live;
  }

  private fitPaths(live: Live) {
    const need = live.spec.runs.length;
    while (live.paths.length < need) {
      const p = document.createElementNS(SVGNS, 'path');
      p.setAttribute('stroke-linejoin', 'round');
      live.g.append(p);
      live.paths.push(p);
    }
    while (live.paths.length > need) live.paths.pop()!.remove();
  }

  private kick() {
    if (!this.raf && this.clouds.size) {
      this.last = performance.now();
      this.raf = requestAnimationFrame(this.frame);
    }
  }

  private frame = (now: number) => {
    this.raf = 0;
    if (document.hidden) return;
    const dt = Math.min(0.1, Math.max(0.001, (now - this.last) / 1000));
    this.last = now;
    if (!this.t0) this.t0 = now;
    const t = this.reduced ? 0 : (now - this.t0) / 1000;
    const settled = this.draw(t, dt);
    // Reduced motion: stop looping once eased in. Otherwise keep breathing while clouds exist.
    if (this.clouds.size && !(this.reduced && settled)) this.raf = requestAnimationFrame(this.frame);
  };

  /** Writes all paths. Returns true when every display value reached its target. */
  private draw(t: number, dt: number): boolean {
    const tau = this.reduced ? 0.09 : 0.13; // ~ 300-450 ms to settle
    const k = 1 - Math.exp(-dt / tau);
    let settled = true;
    for (const [id, live] of this.clouds) {
      const { spec, cur } = live;
      const targetOp = live.leaving ? 0 : Math.min(MAX_FILL, spec.opacity) * (spec.finalized ? 1 : DRAFT_FACTOR);
      cur.opacity += (targetOp - cur.opacity) * k;
      cur.intensity += (spec.intensity - cur.intensity) * k;
      cur.weight += (spec.blendWeight - cur.weight) * k;
      const t1 = hexToRgb(spec.color);
      const t2 = hexToRgb(spec.color2 ?? spec.color);
      for (let i = 0; i < 3; i++) {
        cur.c1[i] += (t1[i] - cur.c1[i]) * k;
        cur.c2[i] += (t2[i] - cur.c2[i]) * k;
      }
      if (Math.abs(targetOp - cur.opacity) > 0.004 || Math.abs(spec.intensity - cur.intensity) > 0.004) settled = false;

      if (live.leaving && cur.opacity < 0.01) {
        live.g.remove();
        live.grad.remove();
        this.clouds.delete(id);
        continue;
      }

      // saturation follows intensity: weak cues look washed, strong cues look rich
      const sat = 0.62 + 0.38 * clamp01(cur.intensity);
      const c1 = desat(cur.c1, sat);
      const c2 = desat(cur.c2, sat);
      const hasBlend = !!spec.color2 && !!spec.blendShape;
      const w = cur.weight;
      const aEnd = Math.max(0, (1 - 2 * w) * 0.9);
      live.stops[0].setAttribute('offset', '0');
      live.stops[0].setAttribute('stop-color', rgbToCss(c1));
      live.stops[1].setAttribute('offset', String(hasBlend ? aEnd : 1));
      live.stops[1].setAttribute('stop-color', rgbToCss(c1));
      live.stops[2].setAttribute('offset', '1');
      live.stops[2].setAttribute('stop-color', rgbToCss(hasBlend ? c2 : c1));

      const style = blendStyles(spec.shape, spec.blendShape ? { shape: spec.blendShape, weight: w } : null);
      const runs = coordinateRuns(spec.runs);
      const fill = `url(#${live.grad.getAttribute('id')})`;
      const stroke = rgbToCss(c1);
      const strokeOp = Math.min(0.95, cur.opacity + 0.3);
      for (let i = 0; i < runs.length; i++) {
        const p = live.paths[i];
        if (!p) continue;
        p.setAttribute(
          'd',
          blobPath(runs[i], style, { seed: live.seed + i * 977, t: t + i * 0.37, intensity: cur.intensity }),
        );
        p.setAttribute('fill', fill);
        p.setAttribute('fill-opacity', cur.opacity.toFixed(3));
        p.setAttribute('stroke', stroke);
        p.setAttribute('stroke-opacity', strokeOp.toFixed(3));
        p.setAttribute('stroke-width', String(spec.selected ? style.stroke + 1.2 : style.stroke));
      }
    }
    return settled;
  }
}

function desat(c: [number, number, number], s: number): [number, number, number] {
  const l = 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2];
  return [l + (c[0] - l) * s, l + (c[1] - l) * s, l + (c[2] - l) * s];
}
