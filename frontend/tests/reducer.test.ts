import { describe, expect, it } from 'vitest';
import { applyEvent, expectResetAck, initialState, unbindTransport, type TranscriptState } from '../src/state/reducer';
import { selectAnnotations, selectCenterAndHistory, selectSentences } from '../src/state/selectors';
import { parseReplay } from '../src/protocol/replayClient';
import type { InboundEvent, ReplayManifest, ServerEvent } from '../src/protocol/events';
import { classifyServerEvent } from '../src/protocol/validate';
import { jsonlFiles, readJson, readJsonl, readText } from './helpers';

function run(events: readonly unknown[], from: TranscriptState = initialState) {
  let s = from;
  const outcomes: string[] = [];
  for (const raw of events) {
    const c = classifyServerEvent(raw);
    if (c.kind === 'invalid') throw new Error(c.reason);
    const r = applyEvent(s, c.event as InboundEvent);
    outcomes.push(r.outcome.kind === 'applied' ? 'applied' : `${r.outcome.kind}:${r.outcome.reason}`);
    s = r.state;
  }
  return { state: s, outcomes };
}

const manifest = readJson<ReplayManifest>('manifest.json');

describe('every shared fixture replays to a sane state', () => {
  it.each(jsonlFiles())('%s', (file) => {
    const events = readJsonl<ServerEvent>(file);
    const { state, outcomes } = run(events);
    expect(outcomes.every((o) => o === 'applied')).toBe(true);
    expect(state.sessionId).toBe(events[0].session_id);
    expect(state.lastSeq).toBe(events[events.length - 1].seq);
    expect(state.status?.state).toBe('stopped');
    // Every committed segment appears once; timed segments match their words.
    const ids = state.segments.map((s) => s.segment_id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const seg of state.segments) {
      if (seg.words) expect(seg.words.map((w) => w.text).join(' ')).toBe(seg.text);
    }
    // Every annotation anchors inside its own timed segment.
    for (const a of selectAnnotations(state)) {
      const seg = state.segments.find((s) => s.segment_id === a.segment_id)!;
      expect(seg.words!.some((w) => w.word_id === a.start_word_id)).toBe(true);
      expect(seg.words!.some((w) => w.word_id === a.end_word_id)).toBe(true);
    }
    // Same result through the replay prevalidator.
    const entry = manifest.fixtures.find((f) => f.file === file)!;
    const loaded = parseReplay(entry, readText(file));
    expect(loaded.events.length).toBe(events.length);
    expect(loaded.durationMs).toBe(entry.duration_ms);
  });
});

describe('replay_demo G1 oracle', () => {
  const events = readJsonl<ServerEvent>('replay_demo.jsonl');
  const upTo = (seq: number) => run(events.filter((e) => e.seq <= seq)).state;

  it('seq 3 replaces seq 2 partial in place; seq 4 commits and clears it; seq 5 adds word ids', () => {
    expect(upTo(2).partial?.text).toBe('For the record');
    expect(upTo(3).partial).toMatchObject({ partial_id: 'p-1', text: 'For the record, everyone arrived' });
    const s4 = upTo(4);
    expect(s4.partial).toBeNull();
    expect(s4.segments).toHaveLength(1);
    expect(s4.segments[0].words).toBeNull();
    const s5 = upTo(5);
    expect(s5.segments[0].words?.map((w) => w.word_id)[0]).toBe('seg-1:w0');
    expect(Object.keys(s5.annotations)).toHaveLength(0);
  });

  it('seq 9-12: a-seg-2 red draft, revised, frozen at revision 3; newer partial kept', () => {
    const s9 = upTo(9);
    expect(s9.annotations['a-seg-2']).toMatchObject({ revision: 1, visible: true, final: false });
    expect(s9.annotations['a-seg-2'].payload.start_word_id).toBe('seg-2:w3');
    const s10 = upTo(10);
    expect(s10.annotations['a-seg-2'].revision).toBe(2);
    expect(s10.annotations['a-seg-2'].payload.opacity).toBeGreaterThan(s9.annotations['a-seg-2'].payload.opacity);
    const s12 = upTo(12);
    expect(s12.annotations['a-seg-2']).toMatchObject({ revision: 3, final: true, visible: true });
    expect(s12.partial?.partial_id).toBe('p-3');
  });

  it('final: seg-3..seg-5 in center, seg-1/seg-2 in history with the finalized red annotation', () => {
    const s = upTo(26);
    const { center, history } = selectCenterAndHistory(s.segments, 3);
    expect(center.map((x) => x.segment_id)).toEqual(['seg-3', 'seg-4', 'seg-5']);
    expect(history.map((x) => x.segment_id)).toEqual(['seg-1', 'seg-2']);
    const red = selectAnnotations(s).find((a) => a.annotation_id === 'a-seg-2')!;
    expect(red).toMatchObject({ state: 'final', visible: true, primary: 'angry' });
    expect(s.annotations['a-seg-5'].payload.primary).toBe('happy');
    expect(Object.values(s.annotations).some((a) => a.payload.segment_id === 'seg-4')).toBe(false);
  });
});

describe('other fixtures', () => {
  it('delayed timing applies to seg-1 and keeps newer partial p-2', () => {
    const events = readJsonl<ServerEvent>('replay_delayed_timing.jsonl');
    const timedIdx = events.findIndex((e) => e.type === 'transcript.timed');
    const before = run(events.slice(0, timedIdx)).state;
    const after = run(events.slice(0, timedIdx + 1)).state;
    expect(before.partial).not.toBeNull();
    expect(after.partial).toEqual(before.partial);
    expect(after.segments.find((s) => s.segment_id === 'seg-1')?.timing_state).toBe('timed');
  });

  it('retraction hides the faint draft and finalizes it hidden', () => {
    const { state } = run(readJsonl('replay_retraction.jsonl'));
    expect(state.annotations['a-faint']).toMatchObject({ visible: false, final: true, revision: 3 });
  });

  it('mixed fixture keeps a two-color blend', () => {
    const { state } = run(readJsonl('replay_mixed.jsonl'));
    const a = Object.values(state.annotations)[0].payload;
    expect(a.secondary).not.toBeNull();
    expect(a.blend?.secondary).toBe(a.secondary);
  });

  it('neutral fixture never creates an annotation', () => {
    const { state } = run(readJsonl('replay_neutral.jsonl'));
    expect(Object.keys(state.annotations)).toHaveLength(0);
  });

  it('failures fixture keeps transcript and records warnings', () => {
    const { state } = run(readJsonl('replay_failures.jsonl'));
    expect(state.segments).toHaveLength(2);
    expect(state.notices.map((n) => n.code)).toEqual(['EMOTION_MODEL_UNAVAILABLE', 'SCRIBE_RECONNECTING']);
  });
});

describe('shared stream negative cases', () => {
  interface StreamCase {
    id: string;
    layer: string;
    prefix: unknown[];
    event: unknown;
    expected: 'reject' | 'ignore_duplicate_or_older' | 'ignore_session' | 'ignore_unknown_type';
  }
  const cases = readJson<StreamCase[]>('invalid/cases.json').filter((c) => c.layer === 'stream');

  it.each(cases.map((c) => [c.id, c] as const))('%s', (_id, c) => {
    const { state: before } = run(c.prefix);
    const cls = classifyServerEvent(c.event);
    if (cls.kind === 'invalid') {
      expect(c.expected).toBe('reject');
      return;
    }
    const r = applyEvent(before, cls.event as InboundEvent);
    switch (c.expected) {
      case 'reject':
        expect(r.outcome.kind).toBe('rejected');
        expect(r.state).toBe(before);
        break;
      case 'ignore_duplicate_or_older':
        expect(r.outcome).toEqual({ kind: 'ignored', reason: 'stale_seq' });
        expect(r.state).toBe(before);
        break;
      case 'ignore_session':
        expect(r.outcome).toEqual({ kind: 'ignored', reason: 'other_session' });
        expect(r.state).toBe(before);
        break;
      case 'ignore_unknown_type':
        expect(r.outcome).toEqual({ kind: 'ignored', reason: 'unknown_type' });
        expect(r.state.segments).toBe(before.segments);
        expect(r.state.lastSeq).toBe((c.event as { seq: number }).seq);
        break;
    }
  });

  it('replay prevalidation fails on a fixture containing a known invalid event', () => {
    const c = cases.find((x) => x.id === 'stale_revision')!;
    const text = [...c.prefix, c.event].map((e) => JSON.stringify(e)).join('\n');
    const entry = manifest.fixtures[0];
    expect(() => parseReplay(entry, text)).toThrow(/stale revision/);
  });
});

describe('sequence, session and reset handling', () => {
  const events = readJsonl<ServerEvent>('replay_demo.jsonl');

  it('duplicate and older seq are ignored without mutation', () => {
    const { state } = run(events.slice(0, 10));
    const dup = applyEvent(state, events[9]);
    expect(dup.outcome).toEqual({ kind: 'ignored', reason: 'stale_seq' });
    expect(dup.state).toBe(state);
    const older = applyEvent(state, events[3]);
    expect(older.outcome.kind).toBe('ignored');
    expect(older.state).toBe(state);
  });

  it('accepts seq gaps', () => {
    const subset = events.filter((e) => e.seq !== 2 && e.seq !== 3);
    const { outcomes } = run(subset);
    expect(outcomes.every((o) => o === 'applied')).toBe(true);
  });

  it('ignores non-status events before binding', () => {
    const r = applyEvent(initialState, events[1]);
    expect(r.outcome).toEqual({ kind: 'ignored', reason: 'unbound' });
  });

  it('a session.reset ack under a new id clears state and rebinds; unsolicited reset is rejected', () => {
    const live = readJson<ServerEvent[]>('server_examples.json');
    const { state } = run(events.slice(0, 12));
    const resetEv = live.find((e) => e.type === 'session.reset')!;
    expect(applyEvent(state, resetEv).outcome.kind).toBe('ignored'); // other session, not awaiting
    const r = applyEvent(expectResetAck(state), resetEv);
    expect(r.outcome.kind).toBe('applied');
    expect(r.state.sessionId).toBe(resetEv.session_id);
    expect(r.state.segments).toHaveLength(0);
    expect(r.state.annotations).toEqual({});
    expect(r.state.awaitingResetAck).toBe(false);
    // Old session's late events are ignored.
    expect(applyEvent(r.state, events[12]).outcome).toEqual({ kind: 'ignored', reason: 'other_session' });
  });

  it('unbindTransport keeps content but accepts a new session status', () => {
    const { state } = run(events);
    const live = readJson<ServerEvent[]>('server_examples.json');
    const r = applyEvent(unbindTransport(state), live[0]);
    expect(r.outcome.kind).toBe('applied');
    expect(r.state.segments.length).toBe(state.segments.length);
  });

  it('rejects decreasing issued_at_ms', () => {
    const { state } = run(events.slice(0, 5));
    const bad = { ...events[5], issued_at_ms: 10 } as ServerEvent;
    expect(applyEvent(state, bad).outcome.kind).toBe('rejected');
  });

  it('live server_examples session reaches stopped with warning recorded', () => {
    const live = readJson<ServerEvent[]>('server_examples.json').filter((e) => e.session_id === 's-live');
    const { state, outcomes } = run(live);
    expect(outcomes.every((o) => o === 'applied')).toBe(true);
    expect(state.status?.state).toBe('stopped');
    expect(state.notices[0].code).toBe('EMOTION_INFERENCE_SLOW');
  });
});

describe('sentence selectors', () => {
  const seg = (id: string, text: string) => ({
    segment_id: id,
    text,
    language_code: null,
    timing_state: 'pending' as const,
    words: null,
    committed_seq: 0,
  });

  it('splits one commit into multiple sentences', () => {
    const s = selectSentences([seg('a', 'Hi there. How are you? Fine!')]);
    expect(s.map((x) => x.tokens.map((t) => t.text).join(' '))).toEqual(['Hi there.', 'How are you?', 'Fine!']);
    expect(s.every((x) => x.segment_ids[0] === 'a')).toBe(true);
  });

  it('keeps one sentence intact across two commits', () => {
    const s = selectSentences([seg('a', 'I went to'), seg('b', 'the store. Then home.')]);
    expect(s[0].tokens.map((t) => t.text).join(' ')).toBe('I went to the store.');
    expect(s[0].segment_ids).toEqual(['a', 'b']);
    expect(s[1].complete).toBe(true);
  });

  it('center keeps whole segments for the newest three sentences', () => {
    const segs = [seg('a', 'One.'), seg('b', 'Two. Three.'), seg('c', 'Four.')];
    const { center, history } = selectCenterAndHistory(segs, 3);
    expect(center.map((s) => s.segment_id)).toEqual(['b', 'c']);
    expect(history.map((s) => s.segment_id)).toEqual(['a']);
  });
});

describe('transcript.timed text revision (provider timed text differs from the commit)', () => {
  const env = (seq: number, type: string, payload: unknown) => ({
    schema_version: '1.0',
    type,
    session_id: 'rev',
    seq,
    issued_at_ms: seq * 10,
    payload,
  });
  const status = env(1, 'session.status', {
    state: 'listening',
    mode: 'replay',
    scribe: 'not_required',
    emotion_model: 'not_required',
    detail: null,
  });
  const commit = env(2, 'transcript.committed', {
    segment_id: 'seg-1',
    text: 'Hello there.',
    timing_state: 'pending',
    language_code: null,
  });
  const words = [
    { word_id: 'seg-1:w0', text: 'Hello', start_ms: 0, end_ms: 200 },
    { word_id: 'seg-1:w1', text: 'their.', start_ms: 210, end_ms: 400 },
  ];

  it('replaces the segment text when the timed event carries matching text', () => {
    const timed = env(3, 'transcript.timed', { segment_id: 'seg-1', language_code: 'en', words, text: 'Hello their.' });
    const { state, outcomes } = run([status, commit, timed]);
    expect(outcomes).toEqual(['applied', 'applied', 'applied']);
    expect(state.segments[0].text).toBe('Hello their.');
    expect(state.segments[0].timing_state).toBe('timed');
  });

  it('still rejects differing words without an explicit text', () => {
    const timed = env(3, 'transcript.timed', { segment_id: 'seg-1', language_code: 'en', words });
    const { outcomes } = run([status, commit, timed]);
    expect(outcomes[2]).toMatch(/timed text mismatch/);
  });

  it('rejects an explicit text that the words do not spell', () => {
    const timed = env(3, 'transcript.timed', { segment_id: 'seg-1', language_code: 'en', words, text: 'Hi there.' });
    const { outcomes } = run([status, commit, timed]);
    expect(outcomes[2]).toMatch(/timed text mismatch/);
  });
});
