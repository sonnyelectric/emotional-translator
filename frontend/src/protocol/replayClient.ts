// Replay loading: fetch the manifest and a fixture from the local backend (PROTOCOL Replay HTTP),
// or read the bundled copies of shared/fixtures (static `build:replay`, PLAN D10).
// The whole stream is prevalidated through the same reducer before playback starts, so an
// invalid fixture never mutates app state.
import type { ReplayFixtureEntry, ReplayManifest, ServerEvent } from './events';
import { MAX_FIXTURE_CHARS, classifyServerEvent, parseStrictJson, validateManifest } from './validate';
import { applyEvent, initialState } from '../state/reducer';

export type ReplaySourceKind = 'backend' | 'bundled';

export interface ReplaySource {
  kind: ReplaySourceKind;
  /** Human-readable origin for the provenance line. */
  label: string;
  getManifest(signal?: AbortSignal): Promise<ReplayManifest>;
  getFixtureText(entry: ReplayFixtureEntry, signal?: AbortSignal): Promise<string>;
}

export class ReplayError extends Error {
  constructor(
    message: string,
    public readonly code: string = 'REPLAY_INVALID',
  ) {
    super(message);
  }
}

// ---------- backend HTTP source ----------

export function backendReplaySource(origin: string): ReplaySource {
  const base = origin.replace(/\/+$/, '');
  return {
    kind: 'backend',
    label: `local backend ${base}`,
    async getManifest(signal) {
      const res = await safeFetch(`${base}/api/v1/replay/manifest`, signal);
      const body = await readJsonBody(res);
      const v = validateManifest(body);
      if (!v.ok) throw new ReplayError(`Replay catalog failed validation (${v.reason}).`);
      return v.manifest;
    },
    async getFixtureText(entry, signal) {
      const res = await safeFetch(`${base}/api/v1/replay/${encodeURIComponent(entry.id)}`, signal);
      if (!res.ok) await throwHttpError(res);
      const text = await res.text();
      if (text.length > MAX_FIXTURE_CHARS) throw new ReplayError('Saved fixture is too large.');
      return text;
    },
  };
}

async function safeFetch(url: string, signal?: AbortSignal): Promise<Response> {
  try {
    return await fetch(url, { signal, cache: 'no-store', credentials: 'omit' });
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err;
    throw new ReplayError('The local backend is not reachable for replay.', 'REPLAY_UNREACHABLE');
  }
}

async function throwHttpError(res: Response): Promise<never> {
  let code = res.status === 404 ? 'REPLAY_NOT_FOUND' : 'REPLAY_INVALID';
  let message = `Replay request failed (HTTP ${res.status}).`;
  try {
    const body = parseStrictJson(await res.text()) as { code?: unknown; message?: unknown };
    if (typeof body.code === 'string') code = body.code;
    if (typeof body.message === 'string') message = body.message.slice(0, 512);
  } catch {
    /* keep generic message */
  }
  throw new ReplayError(message, code);
}

async function readJsonBody(res: Response): Promise<unknown> {
  if (!res.ok) await throwHttpError(res);
  try {
    return parseStrictJson(await res.text(), MAX_FIXTURE_CHARS);
  } catch {
    throw new ReplayError('Replay catalog is not valid JSON.');
  }
}

// ---------- bundled source (static replay build and offline fallback) ----------

const bundledManifest = import.meta.glob('../../../shared/fixtures/manifest.json', {
  eager: true,
  import: 'default',
}) as Record<string, unknown>;

const bundledFixtures = import.meta.glob('../../../shared/fixtures/*.jsonl', {
  query: '?raw',
  import: 'default',
}) as Record<string, () => Promise<string>>;

export function bundledReplaySource(): ReplaySource {
  return {
    kind: 'bundled',
    label: 'copy bundled into this page (no backend)',
    async getManifest() {
      const raw = Object.values(bundledManifest)[0];
      const v = validateManifest(raw);
      if (!v.ok) throw new ReplayError(`Bundled catalog failed validation (${v.reason}).`);
      return v.manifest;
    },
    async getFixtureText(entry) {
      const key = Object.keys(bundledFixtures).find((k) => k.endsWith(`/${entry.file}`));
      if (!key) throw new ReplayError('That saved fixture is unavailable.', 'REPLAY_NOT_FOUND');
      return bundledFixtures[key]();
    },
  };
}

// ---------- parse + prevalidate ----------

export interface LoadedReplay {
  entry: ReplayFixtureEntry;
  events: ServerEvent[];
  /** Count of well-formed unknown v1 events skipped. */
  skippedUnknown: number;
  durationMs: number;
  /** Non-fatal observations (e.g. manifest duration mismatch). */
  diagnostics: string[];
}

/**
 * Parse JSONL and validate the whole stream before playback: strict JSON, schema,
 * one session, an opening replay `listening` status, a terminal replay `stopped` status,
 * strictly increasing seq, nondecreasing time, and every semantic reducer check.
 */
export function parseReplay(entry: ReplayFixtureEntry, text: string): LoadedReplay {
  const lines = text.split('\n').filter((l) => l.trim() !== '');
  if (lines.length === 0) throw new ReplayError('Saved fixture is empty.');
  const events: ServerEvent[] = [];
  let skippedUnknown = 0;
  let sessionId: string | null = null;
  let lastSeq = 0;
  let lastAt = -1;
  let state = initialState;

  lines.forEach((line, i) => {
    let value: unknown;
    try {
      value = parseStrictJson(line);
    } catch (err) {
      throw new ReplayError(`Line ${i + 1}: ${(err as Error).message}`);
    }
    const c = classifyServerEvent(value);
    if (c.kind === 'invalid') throw new ReplayError(`Line ${i + 1}: ${c.reason}`);
    const ev = c.event;
    if (sessionId === null) sessionId = ev.session_id;
    else if (ev.session_id !== sessionId) throw new ReplayError(`Line ${i + 1}: event from another session`);
    if (ev.seq <= lastSeq) throw new ReplayError(`Line ${i + 1}: sequence is not increasing`);
    if (ev.issued_at_ms < lastAt) throw new ReplayError(`Line ${i + 1}: time goes backwards`);
    lastSeq = ev.seq;
    lastAt = ev.issued_at_ms;
    const r = applyEvent(state, ev);
    if (r.outcome.kind === 'rejected') throw new ReplayError(`Line ${i + 1}: ${r.outcome.reason}`);
    if (r.outcome.kind === 'ignored' && r.outcome.reason !== 'unknown_type') {
      throw new ReplayError(`Line ${i + 1}: event ignored (${r.outcome.reason})`);
    }
    state = r.state;
    if (c.kind === 'unknown') skippedUnknown++;
    else events.push(c.event);
  });

  const first = events[0];
  const last = events[events.length - 1];
  if (!first || first.type !== 'session.status' || first.payload.state !== 'listening' || first.payload.mode !== 'replay') {
    throw new ReplayError('Saved fixture must open with a replay "listening" status.');
  }
  if (!last || last.type !== 'session.status' || last.payload.state !== 'stopped' || last.payload.mode !== 'replay') {
    throw new ReplayError('Saved fixture must end with a replay "stopped" status.');
  }
  const durationMs = last.issued_at_ms - first.issued_at_ms;
  const diagnostics: string[] = [];
  if (durationMs !== entry.duration_ms) {
    diagnostics.push(`manifest duration ${entry.duration_ms} ms differs from stream ${durationMs} ms`);
  }
  return { entry, events, skippedUnknown, durationMs, diagnostics };
}

export async function loadReplay(source: ReplaySource, entry: ReplayFixtureEntry, signal?: AbortSignal): Promise<LoadedReplay> {
  const text = await source.getFixtureText(entry, signal);
  return parseReplay(entry, text);
}
