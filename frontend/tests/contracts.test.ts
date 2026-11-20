import { describe, expect, it } from 'vitest';
import {
  classifyServerEvent,
  isValidServerEvent,
  parseStrictJson,
  schemaNames,
  validateClientCommand,
  validateManifest,
  validateNamed,
} from '../src/protocol/validate';
import { makeCommand, KNOWN_EVENT_TYPES, type ClientCommandType } from '../src/protocol/events';
import { jsonlFiles, readJson, readJsonl } from './helpers';

interface InvalidCase {
  id: string;
  layer: 'parse' | 'schema' | 'stream';
  schema?: string;
  instance?: unknown;
  raw?: string;
  expected: string;
}

describe('schema registry', () => {
  it('bundles every shared v1 schema without network', () => {
    const names = schemaNames();
    for (const t of KNOWN_EVENT_TYPES) expect(names).toContain(t);
    expect(names).toEqual(expect.arrayContaining(['client-command', 'replay-manifest', 'server-event', 'common', 'health']));
  });
});

describe('valid corpus', () => {
  it.each(jsonlFiles())('every event in %s is a known valid server event', (file) => {
    for (const ev of readJsonl(file)) {
      expect(isValidServerEvent(ev)).toBe(true);
      expect(classifyServerEvent(ev).kind).toBe('known');
    }
  });

  it('server_examples.json events are valid', () => {
    for (const ev of readJson<unknown[]>('server_examples.json')) {
      expect(classifyServerEvent(ev).kind).toBe('known');
    }
  });

  it('client_commands.json and makeCommand() conform to the command schema', () => {
    for (const c of readJson<unknown[]>('client_commands.json')) expect(validateClientCommand(c)).toBe(true);
    const types: ClientCommandType[] = ['session.start', 'session.pause', 'session.resume', 'session.stop', 'session.reset'];
    for (const t of types) expect(validateClientCommand(makeCommand(t))).toBe(true);
  });

  it('manifest validates and its semantic checks pass', () => {
    const r = validateManifest(readJson('manifest.json'));
    expect(r.ok).toBe(true);
  });

  it('http examples validate', () => {
    const h = readJson<{ health: unknown; errors: unknown[] }>('http_examples.json');
    expect(validateNamed('health', h.health)).toBe(true);
    for (const e of h.errors) expect(validateNamed('http-error', e)).toBe(true);
  });

  it('pipeline window examples validate against model-window', () => {
    const p = readJson<{ windows: unknown[] }>('pipeline_examples.json');
    for (const w of p.windows) expect(validateNamed('model-window', w)).toBe(true);
  });
});

describe('invalid corpus (parse + schema layers)', () => {
  const cases = readJson<InvalidCase[]>('invalid/cases.json');

  it.each(cases.filter((c) => c.layer === 'parse').map((c) => [c.id, c] as const))('parse rejects %s', (_id, c) => {
    expect(() => parseStrictJson(c.raw!)).toThrow();
  });

  it.each(cases.filter((c) => c.layer === 'schema').map((c) => [c.id, c] as const))('schema rejects %s', (_id, c) => {
    if (c.schema === 'client-command') {
      expect(validateClientCommand(c.instance)).toBe(false);
    } else {
      expect(isValidServerEvent(c.instance)).toBe(false);
      const k = classifyServerEvent(c.instance).kind;
      // An unsupported version fails the envelope; known-type shape errors are "invalid".
      expect(k).toBe('invalid');
    }
  });

  it('classifies a well-formed unknown v1 type as unknown, not invalid', () => {
    const c = classifyServerEvent({
      schema_version: '1.0',
      type: 'future.notice',
      session_id: 's',
      seq: 3,
      issued_at_ms: 1,
      payload: { detail: 'x' },
    });
    expect(c.kind).toBe('unknown');
  });

  it('rejects oversized input', () => {
    expect(() => parseStrictJson('"' + 'x'.repeat(300_000) + '"')).toThrow();
  });
});
