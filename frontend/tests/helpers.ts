import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

export const FIXTURES = fileURLToPath(new URL('../../shared/fixtures/', import.meta.url));

export function readJson<T = unknown>(name: string): T {
  return JSON.parse(readFileSync(join(FIXTURES, name), 'utf8')) as T;
}

export function readText(name: string): string {
  return readFileSync(join(FIXTURES, name), 'utf8');
}

export function jsonlFiles(): string[] {
  return readdirSync(FIXTURES).filter((f) => f.endsWith('.jsonl'));
}

export function readJsonl<T = unknown>(name: string): T[] {
  return readText(name)
    .split('\n')
    .filter((l) => l.trim())
    .map((l) => JSON.parse(l) as T);
}
