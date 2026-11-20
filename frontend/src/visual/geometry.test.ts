import { describe, expect, it } from 'vitest';
import {
  SHAPE_STYLES,
  blendStyles,
  blobPath,
  blobPoints,
  coordinateRuns,
  hashSeed,
  lineRuns,
  rng,
  type Run,
} from './geometry';
import type { CloudShape } from './contract';

const run: Run = { x: 40, y: 20, w: 320, h: 44 };
const shapes = Object.keys(SHAPE_STYLES) as CloudShape[];

describe('rng/hash', () => {
  it('is deterministic', () => {
    expect(hashSeed('a-seg1-2')).toBe(hashSeed('a-seg1-2'));
    expect(hashSeed('a')).not.toBe(hashSeed('b'));
    const a = rng(5);
    const b = rng(5);
    expect([a(), a(), a()]).toEqual([b(), b(), b()]);
  });
});

describe('blobPath', () => {
  it.each(shapes)('%s is deterministic and finite', (s) => {
    const o = { seed: 123, t: 1.7, intensity: 0.6 };
    const p1 = blobPath(run, SHAPE_STYLES[s], o);
    expect(p1).toBe(blobPath(run, SHAPE_STYLES[s], o));
    expect(p1).not.toMatch(/NaN|Infinity/);
    expect(p1.startsWith('M')).toBe(true);
    expect(p1.endsWith('Z')).toBe(true);
  });

  it('silhouettes are pairwise distinct', () => {
    const paths = shapes.map((s) => blobPath(run, SHAPE_STYLES[s], { seed: 9, t: 0, intensity: 0.5 }));
    expect(new Set(paths).size).toBe(shapes.length);
  });

  it('jagged uses straight segments, rounded uses curves', () => {
    const o = { seed: 1, t: 0, intensity: 0.5 };
    expect(blobPath(run, SHAPE_STYLES.jagged, o)).toMatch(/L/);
    expect(blobPath(run, SHAPE_STYLES.jagged, o)).not.toMatch(/C/);
    expect(blobPath(run, SHAPE_STYLES.rounded, o)).toMatch(/C/);
  });

  it('seed and time change the shape; same time does not', () => {
    const a = blobPath(run, SHAPE_STYLES.rounded, { seed: 1, t: 0, intensity: 0.5 });
    expect(blobPath(run, SHAPE_STYLES.rounded, { seed: 2, t: 0, intensity: 0.5 })).not.toBe(a);
    expect(blobPath(run, SHAPE_STYLES.rounded, { seed: 1, t: 1.3, intensity: 0.5 })).not.toBe(
      blobPath(run, SHAPE_STYLES.rounded, { seed: 1, t: 0, intensity: 0.5 }),
    );
  });

  it('intensity grows the cloud', () => {
    const ext = (i: number) => {
      const ys = blobPoints(run, SHAPE_STYLES.rounded, { seed: 1, t: 0, intensity: i }).map((p) => p[1]);
      return Math.max(...ys) - Math.min(...ys);
    };
    expect(ext(1)).toBeGreaterThan(ext(0));
  });

  it('keeps points near the text rect', () => {
    const pts = blobPoints(run, SHAPE_STYLES.jagged, { seed: 4, t: 0, intensity: 1 });
    for (const [x, y] of pts) {
      expect(x).toBeGreaterThan(run.x - 80);
      expect(x).toBeLessThan(run.x + run.w + 80);
      expect(y).toBeGreaterThan(run.y - 60);
      expect(y).toBeLessThan(run.y + run.h + 60);
    }
  });
});

describe('blendStyles', () => {
  it('weight 0 or null returns primary, weight interpolates', () => {
    expect(blendStyles('jagged', null)).toEqual(SHAPE_STYLES.jagged);
    const m = blendStyles('jagged', { shape: 'rounded', weight: 0.4 });
    expect(m.spike).toBeLessThan(1);
    expect(m.spike).toBeGreaterThan(0);
  });
});

describe('lineRuns', () => {
  const origin = { left: 10, top: 10 };
  it('merges rects on one line, splits across lines, drops slivers', () => {
    const rects = [
      { left: 110, top: 30, width: 60, height: 30 },
      { left: 50, top: 31, width: 50, height: 28 },
      { left: 170, top: 30, width: 0.2, height: 30 },
      { left: 30, top: 70, width: 90, height: 30 },
    ];
    const runs = lineRuns(rects, origin);
    expect(runs).toHaveLength(2);
    expect(runs[0]).toEqual({ x: 40, y: 20, w: 120, h: 30 });
    expect(runs[1].y).toBe(60);
  });
  it('is stable under input order', () => {
    const rects = [
      { left: 0, top: 0, width: 10, height: 20 },
      { left: 12, top: 1, width: 10, height: 20 },
      { left: 0, top: 40, width: 10, height: 20 },
    ];
    expect(lineRuns([...rects].reverse(), { left: 0, top: 0 })).toEqual(lineRuns(rects, { left: 0, top: 0 }));
  });
  it('coordinateRuns extends all but the last run', () => {
    const r = coordinateRuns([run, run]);
    expect(r[0].h).toBeGreaterThan(run.h);
    expect(r[1].h).toBe(run.h);
  });
});
