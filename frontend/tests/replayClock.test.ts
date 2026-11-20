import { describe, expect, it } from 'vitest';
import { FakeClock, ReplayPlayer, type ReplayPhase } from '../src/replay/clock';
import { readJsonl } from './helpers';
import type { ServerEvent } from '../src/protocol/events';

function setup() {
  const clock = new FakeClock();
  const events = readJsonl<ServerEvent>('replay_demo.jsonl');
  const seen: number[] = [];
  const phases: ReplayPhase[] = [];
  const player = new ReplayPlayer(events, (e) => seen.push(e.seq), (p) => phases.push(p), clock);
  return { clock, events, seen, phases, player };
}

describe('ReplayPlayer', () => {
  it('delivers events at relative issued_at_ms, in order, then finishes', () => {
    const { clock, seen, phases, player } = setup();
    player.play();
    expect(seen).toEqual([1]); // issued_at 0 fires immediately
    clock.advance(419);
    expect(seen).toEqual([1]);
    clock.advance(1);
    expect(seen).toEqual([1, 2]);
    clock.advance(18600);
    expect(seen).toEqual(Array.from({ length: 26 }, (_, i) => i + 1));
    expect(phases.at(-1)).toBe('replay_done');
    expect(clock.pending()).toBe(0);
  });

  it('pause keeps cursor and remaining delay; resume preserves order', () => {
    const { clock, seen, player } = setup();
    player.play();
    clock.advance(700); // seq 2 at 420 fired; seq 3 due at 960 (260 ms left)
    expect(seen).toEqual([1, 2]);
    player.pause();
    expect(player.state).toBe('replay_paused');
    clock.advance(10_000);
    expect(seen).toEqual([1, 2]); // nothing moves while paused
    player.resume();
    clock.advance(259);
    expect(seen).toEqual([1, 2]);
    clock.advance(1);
    expect(seen).toEqual([1, 2, 3]);
  });

  it('stop cancels pending timers and keeps what was delivered', () => {
    const { clock, seen, player } = setup();
    player.play();
    clock.advance(2500);
    const n = seen.length;
    player.stop();
    expect(player.state).toBe('replay_done');
    clock.advance(30_000);
    expect(seen.length).toBe(n);
    expect(clock.pending()).toBe(0);
  });

  it('is deterministic across repeated runs', () => {
    const a = setup();
    a.player.play();
    a.clock.advance(5000);
    a.player.pause();
    a.clock.advance(333);
    a.player.resume();
    a.clock.advance(20_000);
    const b = setup();
    b.player.play();
    b.clock.advance(5000);
    b.player.pause();
    b.clock.advance(333);
    b.player.resume();
    b.clock.advance(20_000);
    expect(a.seen).toEqual(b.seen);
  });

  it('dispose stops callbacks (reset)', () => {
    const { clock, seen, player } = setup();
    player.play();
    player.dispose();
    clock.advance(30_000);
    expect(seen).toEqual([1]);
  });
});
