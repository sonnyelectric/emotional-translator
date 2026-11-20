// Live capture with Chrome's fake microphone and a mocked backend WebSocket.
import { expect, test, type WebSocketRoute } from '@playwright/test';
import { BACKEND } from './e2e-helpers';

const WS_URL = BACKEND.replace('http', 'ws') + '/ws/v1/session';

function status(seq: number, at: number, state: string, extra: Record<string, unknown> = {}) {
  return JSON.stringify({
    schema_version: '1.0',
    type: 'session.status',
    session_id: 's-mock',
    seq,
    issued_at_ms: at,
    payload: { state, mode: 'live', scribe: state === 'listening' ? 'connected' : 'connecting', emotion_model: 'ready', detail: null, ...extra },
  });
}
const FORMAT = { sample_rate_hz: 16000, channels: 1, sample_format: 's16le' };

test.describe('mic', () => {
  test('mic: waits for listening, sends 1,280-byte PCM frames, drains before pause, stops cleanly', async ({ page }) => {
    const log: string[] = [];
    const frames: number[] = [];
    let ws!: WebSocketRoute;
    let seq = 0;
    await page.routeWebSocket(WS_URL, (route) => {
      ws = route;
      route.onMessage((m) => {
        if (typeof m === 'string') {
          const cmd = JSON.parse(m) as { type: string };
          log.push(`cmd:${cmd.type}:${frames.length}`);
          if (cmd.type === 'session.start') {
            route.send(status(++seq, 0, 'connecting'));
          } else if (cmd.type === 'session.pause') {
            route.send(status(++seq, 2000, 'paused', { scribe: 'disconnected' }));
          } else if (cmd.type === 'session.resume') {
            route.send(status(++seq, 2100, 'connecting'));
            route.send(status(++seq, 2200, 'listening', FORMAT));
          } else if (cmd.type === 'session.stop') {
            route.send(status(++seq, 5000, 'stopping'));
            route.send(status(++seq, 5100, 'stopped', { scribe: 'disconnected' }));
            route.close({ code: 1000 });
          }
        } else {
          frames.push(m.length);
        }
      });
    });
    await page.goto('/');
    await expect(page.getByTestId('mode-badge')).toHaveText('LIVE');
    await page.getByTestId('btn-start').click();
    await expect.poll(() => log[0]).toBe('cmd:session.start:0');
    await page.waitForTimeout(500);
    expect(frames.length).toBe(0); // gated until listening
    ws.send(status(++seq, 300, 'listening', FORMAT));
    await expect(page.getByTestId('status-pill')).toContainText('Listening');
    await expect.poll(() => frames.length, { timeout: 5000 }).toBeGreaterThan(10);
    const full = frames.filter((n) => n === 1280).length;
    expect(full).toBeGreaterThan(10);
    expect(frames.every((n) => n % 2 === 0 && n >= 640 && n <= 3200)).toBe(true);
    // Real-time rate check: 16 kHz output = 25 frames of 40 ms per second.
    const c0 = frames.length;
    const t0 = Date.now();
    await page.waitForTimeout(3000);
    const rate = (frames.length - c0) / ((Date.now() - t0) / 1000);
    console.log(`observed PCM frame rate: ${rate.toFixed(1)} frames/s (${((rate * 640) / 1000).toFixed(2)} k samples/s)`);
    expect(rate).toBeGreaterThan(21);
    expect(rate).toBeLessThan(29);

    await page.getByTestId('btn-pause').click();
    await expect(page.getByTestId('status-pill')).toContainText('Paused');
    const atPause = frames.length;
    const pauseLog = log.find((l) => l.startsWith('cmd:session.pause'))!;
    expect(Number(pauseLog.split(':')[2])).toBe(atPause); // all frames sent before the control
    await page.waitForTimeout(600);
    expect(frames.length).toBe(atPause); // nothing while paused

    await page.getByTestId('btn-resume').click();
    await expect.poll(() => frames.length, { timeout: 5000 }).toBeGreaterThan(atPause + 5);

    await page.getByTestId('btn-stop').click();
    await expect(page.getByTestId('status-pill')).toContainText('Stopped');
    const atStop = frames.length;
    await page.waitForTimeout(600);
    expect(frames.length).toBe(atStop);
    await expect(page.getByTestId('btn-reset')).toBeEnabled();
    await expect(page.getByRole('radio', { name: 'Replay' })).toBeDisabled();
    await page.getByTestId('btn-reset').click();
    await expect(page.getByTestId('btn-start')).toBeEnabled();
  });

  test('mic: permission denial stays in the frontend with a clear message and no socket', async ({ page }) => {
    let opened = 0;
    await page.routeWebSocket(WS_URL, () => {
      opened++;
    });
    await page.addInitScript(() => {
      navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException('denied', 'NotAllowedError'));
    });
    await page.goto('/');
    await page.getByTestId('btn-start').click();
    await expect(page.getByTestId('notices')).toContainText('Microphone blocked');
    expect(opened).toBe(0);
    await expect(page.getByTestId('btn-start')).toBeEnabled();
  });

  test('mic: fatal session.error keeps text and offers Replay', async ({ page }) => {
    await page.routeWebSocket(WS_URL, (route) => {
      route.onMessage((m) => {
        if (typeof m === 'string' && JSON.parse(m).type === 'session.start') {
          route.send(status(1, 0, 'connecting'));
          route.send(
            JSON.stringify({
              schema_version: '1.0',
              type: 'session.error',
              session_id: 's-mock',
              seq: 2,
              issued_at_ms: 5,
              payload: { code: 'SCRIBE_AUTH', message: 'Transcription credentials were rejected.', recoverable: false },
            }),
          );
          route.send(status(3, 6, 'error', { scribe: 'failed' }));
          route.close({ code: 1000 });
        }
      });
    });
    await page.goto('/');
    await page.getByTestId('btn-start').click();
    await expect(page.getByTestId('notices')).toContainText('rejected the API key');
    await page.getByRole('button', { name: 'Switch to Replay' }).first().click();
    await expect(page.getByTestId('mode-badge')).toHaveText('REPLAY');
  });
});
