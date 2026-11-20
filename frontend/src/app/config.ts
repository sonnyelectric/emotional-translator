// Public, non-secret frontend configuration. Never put provider keys in VITE_* variables.

export const STATIC_REPLAY: boolean = typeof __STATIC_REPLAY__ !== 'undefined' && __STATIC_REPLAY__;

const DEFAULT_BACKEND = 'http://127.0.0.1:8000';
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]', '::1']);

function parseOrigin(raw: string | null | undefined): URL | null {
  if (!raw) return null;
  try {
    const u = new URL(raw.trim());
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return null;
    if (u.username || u.password) return null;
    return u;
  } catch {
    return null;
  }
}

/** Accept only loopback http(s) origins (the `?backend=` query: a link cannot point a page elsewhere). */
export function sanitizeOrigin(raw: string | null | undefined): string | null {
  const u = parseOrigin(raw);
  if (!u || !LOOPBACK_HOSTS.has(u.hostname)) return null;
  return `${u.protocol}//${u.host}`;
}

/**
 * Accept the build-time backend origin: any https origin (a hosted backend), or http only
 * for loopback. Plain http to a remote host is refused: browsers block it from an https page
 * and the microphone stream would travel unencrypted.
 */
export function sanitizeConfiguredOrigin(raw: string | null | undefined): string | null {
  const u = parseOrigin(raw);
  if (!u) return null;
  if (u.protocol === 'http:' && !LOOPBACK_HOSTS.has(u.hostname)) return null;
  return `${u.protocol}//${u.host}`;
}

/**
 * Backend HTTP origin: `?backend=` (loopback only, for side-by-side dev ports), then
 * VITE_BACKEND_HTTP_ORIGIN (https anywhere, or loopback http), then the protocol default.
 * The WebSocket URL is derived from it (https -> wss, http -> ws).
 */
export function backendOrigin(): string {
  let fromQuery: string | null = null;
  try {
    fromQuery = new URLSearchParams(window.location.search).get('backend');
  } catch {
    /* no window in tests */
  }
  return (
    sanitizeOrigin(fromQuery) ?? sanitizeConfiguredOrigin(import.meta.env.VITE_BACKEND_HTTP_ORIGIN) ?? DEFAULT_BACKEND
  );
}

/** `?diag=1` enables capture timing diagnostics in the developer console. */
export function diagnosticsEnabled(): boolean {
  try {
    return new URLSearchParams(window.location.search).get('diag') === '1';
  } catch {
    return false;
  }
}
