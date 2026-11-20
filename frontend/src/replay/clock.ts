// Replay scheduler with an injectable clock so tests can drive time deterministically.
// Events are scheduled by their relative `issued_at_ms`. Pause keeps the cursor and the
// remaining delay to the next event; Stop cancels timers and keeps rendered content.

export interface Clock {
  now(): number;
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
}

export const realClock: Clock = {
  now: () => performance.now(),
  setTimeout: (fn, ms) => globalThis.setTimeout(fn, ms),
  clearTimeout: (h) => globalThis.clearTimeout(h as ReturnType<typeof setTimeout>),
};

export type ReplayPhase = 'replay_idle' | 'replay_playing' | 'replay_paused' | 'replay_done';

export interface Timed {
  issued_at_ms: number;
}

export class ReplayPlayer<E extends Timed> {
  private cursor = 0;
  /** Replay-timeline position (ms relative to first event) at `anchorWall`. */
  private position = 0;
  private anchorWall = 0;
  private timer: unknown = null;
  private phase: ReplayPhase = 'replay_idle';
  private readonly origin: number;

  constructor(
    private readonly events: readonly E[],
    private readonly onEvent: (e: E, index: number) => void,
    private readonly onPhase: (p: ReplayPhase) => void,
    private readonly clock: Clock = realClock,
    private readonly speed = 1,
  ) {
    this.origin = events.length > 0 ? events[0].issued_at_ms : 0;
  }

  get state(): ReplayPhase {
    return this.phase;
  }

  get index(): number {
    return this.cursor;
  }

  /** Current replay-timeline position in ms. */
  elapsed(): number {
    if (this.phase === 'replay_playing') return this.position + (this.clock.now() - this.anchorWall) * this.speed;
    return this.position;
  }

  play(): void {
    if (this.phase !== 'replay_idle') return;
    this.position = 0;
    this.anchorWall = this.clock.now();
    this.setPhase('replay_playing');
    this.pump();
  }

  pause(): void {
    if (this.phase !== 'replay_playing') return;
    this.position = this.elapsed();
    this.cancelTimer();
    this.setPhase('replay_paused');
  }

  resume(): void {
    if (this.phase !== 'replay_paused') return;
    this.anchorWall = this.clock.now();
    this.setPhase('replay_playing');
    this.pump();
  }

  /** Cancel pending events; keeps whatever was already delivered. */
  stop(): void {
    if (this.phase === 'replay_done' || this.phase === 'replay_idle') {
      this.cancelTimer();
      if (this.phase === 'replay_idle') this.setPhase('replay_done');
      return;
    }
    this.position = this.elapsed();
    this.cancelTimer();
    this.setPhase('replay_done');
  }

  /** Cancel everything without emitting phase changes (used on Reset/unmount). */
  dispose(): void {
    this.cancelTimer();
    this.phase = 'replay_done';
  }

  private setPhase(p: ReplayPhase) {
    this.phase = p;
    this.onPhase(p);
  }

  private cancelTimer() {
    if (this.timer !== null) {
      this.clock.clearTimeout(this.timer);
      this.timer = null;
    }
  }

  private pump = (): void => {
    this.timer = null;
    if (this.phase !== 'replay_playing') return;
    const now = this.elapsed();
    while (this.cursor < this.events.length) {
      const e = this.events[this.cursor];
      const due = e.issued_at_ms - this.origin;
      if (due > now) break;
      const i = this.cursor++;
      this.onEvent(e, i);
      if (this.phase !== 'replay_playing') return; // handler paused/stopped us
    }
    if (this.cursor >= this.events.length) {
      this.position = now;
      this.setPhase('replay_done');
      return;
    }
    const next = this.events[this.cursor].issued_at_ms - this.origin;
    this.timer = this.clock.setTimeout(this.pump, Math.max(0, (next - now) / this.speed));
  };
}

/** Deterministic manual clock for tests. */
export class FakeClock implements Clock {
  private t = 0;
  private nextId = 1;
  private timers = new Map<number, { at: number; fn: () => void }>();

  now(): number {
    return this.t;
  }
  setTimeout(fn: () => void, ms: number): unknown {
    const id = this.nextId++;
    this.timers.set(id, { at: this.t + ms, fn });
    return id;
  }
  clearTimeout(handle: unknown): void {
    this.timers.delete(handle as number);
  }
  pending(): number {
    return this.timers.size;
  }
  /** Advance time, firing due timers in order. */
  advance(ms: number): void {
    const target = this.t + ms;
    for (;;) {
      let bestId = -1;
      let best: { at: number; fn: () => void } | null = null;
      for (const [id, tm] of this.timers) {
        if (tm.at <= target && (!best || tm.at < best.at || (tm.at === best.at && id < bestId))) {
          best = tm;
          bestId = id;
        }
      }
      if (!best) break;
      this.timers.delete(bestId);
      this.t = best.at;
      best.fn();
    }
    this.t = target;
  }
}
