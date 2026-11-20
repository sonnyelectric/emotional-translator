import { afterEach, describe, expect, it, vi } from 'vitest';
import { backendOrigin, sanitizeConfiguredOrigin, sanitizeOrigin } from '../src/app/config';
import { wsUrlFromHttpOrigin } from '../src/protocol/liveClient';
import { tuneUrl } from '../src/tune/TunePage';

const REPLIT = 'https://emotional-translator-justinwang221.replit.app';

describe('sanitizeConfiguredOrigin (VITE_BACKEND_HTTP_ORIGIN)', () => {
  it.each([
    [REPLIT, REPLIT],
    [`${REPLIT}/`, REPLIT],
    [`${REPLIT}/some/path?x=1`, REPLIT],
    ['https://api.example.com:8443', 'https://api.example.com:8443'],
    ['http://127.0.0.1:8000', 'http://127.0.0.1:8000'],
    ['http://localhost:8400', 'http://localhost:8400'],
    ['http://[::1]:8000', 'http://[::1]:8000'],
    // Bare host entered in a hosting dashboard (no scheme): https for remote, http for loopback.
    ['emotional-translator-1.replit.app', 'https://emotional-translator-1.replit.app'],
    [' emotional-translator-1.replit.app/ ', 'https://emotional-translator-1.replit.app'],
    ['localhost:8000', 'http://localhost:8000'],
    ['127.0.0.1:8000', 'http://127.0.0.1:8000'],
  ])('accepts %s', (raw, expected) => {
    expect(sanitizeConfiguredOrigin(raw)).toBe(expected);
  });

  it.each([
    'http://api.example.com', // remote plain http
    'ws://127.0.0.1:8000',
    'javascript:alert(1)',
    'https://user:pw@api.example.com',
    'not a url',
    '',
    undefined,
  ])('refuses %s', (raw) => {
    expect(sanitizeConfiguredOrigin(raw as string | undefined)).toBeNull();
  });
});

describe('sanitizeOrigin (?backend= query) stays loopback-only', () => {
  it('accepts loopback', () => {
    expect(sanitizeOrigin('http://127.0.0.1:8400')).toBe('http://127.0.0.1:8400');
    expect(sanitizeOrigin('https://localhost:8443')).toBe('https://localhost:8443');
  });
  it.each([REPLIT, 'https://evil.example', 'http://192.168.1.2:8000'])('refuses %s', (raw) => {
    expect(sanitizeOrigin(raw)).toBeNull();
  });
});

describe('backendOrigin', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it('uses an https VITE_BACKEND_HTTP_ORIGIN', () => {
    vi.stubEnv('VITE_BACKEND_HTTP_ORIGIN', REPLIT);
    expect(backendOrigin()).toBe(REPLIT);
  });

  it('falls back to the loopback default for a remote http origin', () => {
    vi.stubEnv('VITE_BACKEND_HTTP_ORIGIN', 'http://api.example.com');
    expect(backendOrigin()).toBe('http://127.0.0.1:8000');
  });

  it('lets a loopback ?backend= override, but never a remote one', () => {
    vi.stubEnv('VITE_BACKEND_HTTP_ORIGIN', REPLIT);
    vi.stubGlobal('window', { location: { search: '?backend=http://127.0.0.1:8400' } });
    expect(backendOrigin()).toBe('http://127.0.0.1:8400');
    vi.stubGlobal('window', { location: { search: '?backend=https://evil.example' } });
    expect(backendOrigin()).toBe(REPLIT);
  });
});

describe('WebSocket URLs follow the HTTP scheme', () => {
  it('derives wss:// from https and ws:// from http', () => {
    expect(wsUrlFromHttpOrigin(REPLIT)).toBe('wss://emotional-translator-justinwang221.replit.app/ws/v1/session');
    expect(wsUrlFromHttpOrigin('http://127.0.0.1:8000')).toBe('ws://127.0.0.1:8000/ws/v1/session');
    expect(tuneUrl(REPLIT)).toBe('wss://emotional-translator-justinwang221.replit.app/ws/dev/tune');
  });
});
