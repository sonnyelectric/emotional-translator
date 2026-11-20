// Strict, no-network Draft 2020-12 validation against the local shared/schemas/v1 files.
// The schema `$id` URLs are identifiers only: every file is registered from the bundle,
// so Ajv never fetches anything.
import Ajv2020, { type ValidateFunction, type ErrorObject } from 'ajv/dist/2020';
import {
  KNOWN_EVENT_TYPES,
  type ClientCommand,
  type InboundEvent,
  type ReplayManifest,
  type ServerEvent,
  type UnknownEvent,
} from './events';

const schemaModules = import.meta.glob('../../../shared/schemas/v1/*.schema.json', {
  eager: true,
  import: 'default',
}) as Record<string, Record<string, unknown>>;

const SCHEMA_BASE = 'https://emotional-translator.invalid/schemas/v1/';

/** Max size of one inbound text frame or replay line (bytes, approximated by UTF-16 length). */
export const MAX_FRAME_CHARS = 256 * 1024;
/** Max size of a whole replay fixture. */
export const MAX_FIXTURE_CHARS = 8 * 1024 * 1024;

let ajv: Ajv2020 | null = null;
const compiled = new Map<string, ValidateFunction>();

function getAjv(): Ajv2020 {
  if (ajv) return ajv;
  // strict:false because the shared schemas use if/then without `type` and similar
  // patterns Ajv's strict mode warns on; validation semantics are unchanged.
  ajv = new Ajv2020({ strict: false, allErrors: false, validateFormats: false });
  for (const schema of Object.values(schemaModules)) {
    ajv.addSchema(schema);
  }
  return ajv;
}

function validator(name: string): ValidateFunction {
  let v = compiled.get(name);
  if (!v) {
    const fn = getAjv().getSchema(SCHEMA_BASE + name + '.schema.json');
    if (!fn) throw new Error(`Schema not bundled: ${name}`);
    v = fn;
    compiled.set(name, v);
  }
  return v;
}

export function schemaNames(): string[] {
  return Object.values(schemaModules).map((s) => String(s.$id).replace(SCHEMA_BASE, '').replace('.schema.json', ''));
}

function describeErrors(errors: ErrorObject[] | null | undefined): string {
  if (!errors || errors.length === 0) return 'schema mismatch';
  const e = errors[0];
  return `${e.instancePath || '/'} ${e.message ?? 'invalid'}`.slice(0, 200);
}

export class ParseError extends Error {}

/** Recursively rejects non-finite numbers (e.g. 1e9999 parses to Infinity). */
function assertFinite(value: unknown, depth = 0): void {
  if (depth > 64) throw new ParseError('nesting too deep');
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new ParseError('non-finite number');
    return;
  }
  if (Array.isArray(value)) {
    for (const v of value) assertFinite(v, depth + 1);
    return;
  }
  if (value !== null && typeof value === 'object') {
    for (const v of Object.values(value as Record<string, unknown>)) assertFinite(v, depth + 1);
  }
}

/**
 * Strict JSON parse: size limit, standard JSON only (JSON.parse already rejects NaN/Infinity
 * tokens), and recursive rejection of overflowing numbers.
 */
export function parseStrictJson(raw: string, maxChars = MAX_FRAME_CHARS): unknown {
  if (typeof raw !== 'string') throw new ParseError('expected text');
  if (raw.length > maxChars) throw new ParseError('input too large');
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch (err) {
    throw new ParseError(`malformed JSON: ${(err as Error).message}`.slice(0, 200));
  }
  assertFinite(value);
  return value;
}

export type Classification =
  | { kind: 'known'; event: ServerEvent }
  | { kind: 'unknown'; event: UnknownEvent }
  | { kind: 'invalid'; reason: string };

/** Classify a parsed value: invalid, well-formed unknown v1 type, or a schema-valid known event. */
export function classifyServerEvent(value: unknown): Classification {
  const envelope = validator('event-envelope');
  if (!envelope(value)) {
    return { kind: 'invalid', reason: `envelope: ${describeErrors(envelope.errors)}` };
  }
  const obj = value as Record<string, unknown>;
  const type = obj.type as string;
  if (!KNOWN_EVENT_TYPES.has(type)) {
    return { kind: 'unknown', event: { ...(obj as Omit<UnknownEvent, '__unknown'>), __unknown: true } };
  }
  const v = validator(type);
  if (!v(value)) {
    return { kind: 'invalid', reason: `${type}: ${describeErrors(v.errors)}` };
  }
  return { kind: 'known', event: value as ServerEvent };
}

/** Validate against the full `server-event` oneOf (used by contract tests). */
export function isValidServerEvent(value: unknown): value is ServerEvent {
  return validator('server-event')(value) === true;
}

export function validateClientCommand(value: unknown): value is ClientCommand {
  return validator('client-command')(value) === true;
}

export function validateManifest(value: unknown): { ok: true; manifest: ReplayManifest } | { ok: false; reason: string } {
  const v = validator('replay-manifest');
  if (!v(value)) return { ok: false, reason: describeErrors(v.errors) };
  const m = value as ReplayManifest;
  const ids = new Set<string>();
  const files = new Set<string>();
  for (const f of m.fixtures) {
    if (ids.has(f.id) || files.has(f.file)) return { ok: false, reason: `duplicate fixture ${f.id}` };
    if (f.file !== `${f.id}.jsonl`) return { ok: false, reason: `fixture ${f.id} file name mismatch` };
    ids.add(f.id);
    files.add(f.file);
  }
  if (!ids.has(m.default_fixture)) return { ok: false, reason: 'default fixture missing' };
  return { ok: true, manifest: m };
}

export function validateNamed(schemaName: string, value: unknown): boolean {
  return validator(schemaName)(value) === true;
}

/** Parse + classify one text frame. */
export function decodeServerFrame(raw: string): Classification {
  let value: unknown;
  try {
    value = parseStrictJson(raw);
  } catch (err) {
    return { kind: 'invalid', reason: (err as Error).message };
  }
  return classifyServerEvent(value);
}

export type { InboundEvent };
