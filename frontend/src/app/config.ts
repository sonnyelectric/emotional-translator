// Public, non-secret frontend configuration. Never put provider keys in VITE_* variables.

export const STATIC_REPLAY: boolean = typeof __STATIC_REPLAY__ !== 'undefined' && __STATIC_REPLAY__;

const DEFAULT_BACKEND = 'http://127.0.0.1:8000';
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]', '::1']);

/** Accept only loopback http(s) origins: endpoints stay local (PROTOCOL). */
export function sanitizeOrigin(raw: string | null | undefined): string | null {
  if (!raw) return null;
  try {
    const u = new URL(raw);
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return null;
    if (!LOOPBACK_HOSTS.has(u.hostname)) return null;
    return `${u.protocol}//${u.host}`;
  } catch {
    return null;
  }
}

/**
 * Backend HTTP origin: `?backend=` (loopback only, for side-by-side dev ports), then
 * VITE_BACKEND_HTTP_ORIGIN, then the protocol default.
 */
export function backendOrigin(): string {
  let fromQuery: string | null = null;
  try {
    fromQuery = new URLSearchParams(window.location.search).get('backend');
  } catch {
    /* no window in tests */
  }
  return sanitizeOrigin(fromQuery) ?? sanitizeOrigin(import.meta.env.VITE_BACKEND_HTTP_ORIGIN) ?? DEFAULT_BACKEND;
}

/** `?diag=1` enables capture timing diagnostics in the developer console. */
export function diagnosticsEnabled(): boolean {
  try {
    return new URLSearchParams(window.location.search).get('diag') === '1';
  } catch {
    return false;
  }
}
