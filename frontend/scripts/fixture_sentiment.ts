/**
 * Runs the real browser text-sentiment model (same library, model id and dtype as
 * src/mismatch/sentiment.worker.ts) on every committed segment of every replay fixture,
 * rebuilds each segment's final annotations from the fixture events, and reports whether
 * the "Words and voice differ" badge would show (src/mismatch/valence.ts, unchanged logic).
 *
 * Usage (from frontend/): npm run check:fixtures [-- path/to/fixture.jsonl ...]
 * Exits 1 if any segment would show the badge, so it can gate a recorded fixture.
 * The model comes from the local transformers cache or Hugging Face on first run.
 */
import { readFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { pipeline } from '@huggingface/transformers';
import type { Annotation } from '../src/visual/contract';
import { computeMismatch, TEXT_SCORE_MIN } from '../src/mismatch/valence';

const MODEL_ID = 'Xenova/distilbert-base-uncased-finetuned-sst-2-english';
const here = dirname(fileURLToPath(import.meta.url));
const fixturesDir = resolve(here, '../../shared/fixtures');

function fixtureFiles(): string[] {
  const args = process.argv.slice(2).filter((a) => a.endsWith('.jsonl'));
  if (args.length) return args.map((a) => resolve(a));
  const manifest = JSON.parse(readFileSync(join(fixturesDir, 'manifest.json'), 'utf8'));
  return manifest.fixtures.map((f: { file: string }) => join(fixturesDir, f.file));
}

interface SegmentState {
  text: string;
  annotations: Map<string, Annotation>;
}

function finalSegments(file: string): Map<string, SegmentState> {
  const segs = new Map<string, SegmentState>();
  const annSeg = new Map<string, string>();
  for (const line of readFileSync(file, 'utf8').split('\n')) {
    if (!line.trim()) continue;
    const ev = JSON.parse(line);
    const p = ev.payload;
    if (ev.type === 'transcript.committed') {
      segs.set(p.segment_id, { text: p.text, annotations: segs.get(p.segment_id)?.annotations ?? new Map() });
    } else if (ev.type === 'emotion.updated') {
      annSeg.set(p.annotation_id, p.segment_id);
      segs.get(p.segment_id)?.annotations.set(p.annotation_id, p as Annotation);
    } else if (ev.type === 'emotion.retracted') {
      const sid = annSeg.get(p.annotation_id);
      if (sid) segs.get(sid)?.annotations.delete(p.annotation_id);
    }
  }
  return segs;
}

const classify = (await pipeline('sentiment-analysis', MODEL_ID, { dtype: 'q8' })) as unknown as (
  t: string,
) => Promise<Array<{ label: string; score: number }>>;

let flagged = 0;
console.log(`model ${MODEL_ID} q8; badge gate ${TEXT_SCORE_MIN}`);
console.log('| Fixture | Segment | Text | Label | Score | Dominant visible voice | Badge |');
console.log('|---|---|---|---|---|---|---|');
for (const file of fixtureFiles()) {
  for (const [sid, s] of finalSegments(file)) {
    const [out] = await classify(s.text);
    const r = computeMismatch(sid, s.text, { label: out.label, score: out.score }, [...s.annotations.values()]);
    if (r.differs) flagged++;
    console.log(
      `| ${basename(file, '.jsonl')} | ${sid} | "${s.text}" | ${out.label} | ${out.score.toFixed(5)} | ${r.voice ?? 'none'} | ${r.differs ? '**YES**' : 'no'} |`,
    );
  }
}
console.log(`\n${flagged} segment(s) would show the badge.`);
process.exit(flagged ? 1 : 0);
