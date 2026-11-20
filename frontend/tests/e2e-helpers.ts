import type { Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

const FIXTURES = fileURLToPath(new URL('../../shared/fixtures/', import.meta.url));
export const BACKEND = process.env.E2E_BACKEND ?? 'http://127.0.0.1:8000';

/** Record any WebSocket or getUserMedia use so replay tests can assert there is none. */
export async function instrument(page: Page) {
  await page.addInitScript(() => {
    const w = window as unknown as { __wsOpened: number; __gumCalls: number };
    w.__wsOpened = 0;
    w.__gumCalls = 0;
    const OrigWS = window.WebSocket;
    window.WebSocket = class extends OrigWS {
      constructor(url: string | URL, protocols?: string | string[]) {
        super(url, protocols);
        // Count app sockets only (Vite's dev HMR socket is not part of the app).
        if (String(url).includes('/ws/v1/')) w.__wsOpened++;
      }
    } as typeof WebSocket;
    const md = navigator.mediaDevices;
    if (md?.getUserMedia) {
      const orig = md.getUserMedia.bind(md);
      md.getUserMedia = (c?: MediaStreamConstraints) => {
        w.__gumCalls++;
        return orig(c);
      };
    }
  });
}

/** Serve the checked-in fixtures in place of the backend replay endpoints (unless E2E_REAL_REPLAY=1). */
/** `manifestOverride` replaces the tracked manifest body (UI-labelling tests only). */
export async function stubReplay(page: Page, requests: string[] = [], manifestOverride?: unknown) {
  if (process.env.E2E_REAL_REPLAY === '1') return;
  await page.route(`${BACKEND}/api/v1/replay/**`, async (route) => {
    const url = new URL(route.request().url());
    requests.push(url.pathname);
    const id = url.pathname.split('/').pop()!;
    if (id === 'manifest') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: { 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store' },
        body: manifestOverride ? JSON.stringify(manifestOverride) : readFileSync(join(FIXTURES, 'manifest.json'), 'utf8'),
      });
    }
    try {
      const body = readFileSync(join(FIXTURES, `${id}.jsonl`), 'utf8');
      return route.fulfill({
        status: 200,
        contentType: 'application/x-ndjson',
        headers: { 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store' },
        body,
      });
    } catch {
      return route.fulfill({
        status: 404,
        contentType: 'application/json',
        headers: { 'Access-Control-Allow-Origin': '*' },
        body: JSON.stringify({ code: 'REPLAY_NOT_FOUND', message: 'That saved fixture is unavailable.' }),
      });
    }
  });
}
