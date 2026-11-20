import { expect, test } from '@playwright/test';
import { instrument, stubReplay } from './e2e-helpers';

test.describe('G1 replay', () => {
  test('G1 plays replay_demo with REPLAY label, no mic or WebSocket, history and reset', async ({ page }) => {
    const requests: string[] = [];
    await instrument(page);
    await stubReplay(page, requests);
    await page.goto('/');
    await page.getByRole('radio', { name: 'Replay' }).click();
    await expect(page.getByTestId('replay-banner')).toContainText('REPLAY');
    await expect(page.getByTestId('mode-badge')).toHaveText('REPLAY');
    await expect(page.getByTestId('fixture-select')).toHaveValue('replay_demo');
    await page.getByTestId('btn-start').click();
    await expect(page.getByTestId('replay-provenance')).toContainText('Synthetic example');

    // Seq 2-3 partial replacement, then seq 4 commit.
    await expect(page.locator('[data-partial-id="p-1"]')).toContainText('For the record');
    await expect(page.locator('[data-segment-id="seg-1"]')).toBeVisible({ timeout: 5000 });

    // Seq 9: annotation starts at word 3 of seg-2.
    const red = page.locator('[data-annotation-id="a-seg-2"]');
    await expect(red).toBeVisible({ timeout: 8000 });
    await expect(red.locator('[data-word-id]').first()).toHaveAttribute('data-word-id', 'seg-2:w3');
    await expect(red).toContainText('and I am tired of being ignored.');

    // Pause holds the cursor.
    await page.getByTestId('btn-pause').click();
    await expect(page.getByTestId('status-pill')).toContainText('Replay paused');
    const frozen = await page.getByTestId('center-transcript').innerText();
    await page.waitForTimeout(1500);
    expect(await page.getByTestId('center-transcript').innerText()).toBe(frozen);
    await page.getByTestId('btn-resume').click();

    // Finish: seg-3..seg-5 centered, seg-4 plain, gold cloud on seg-5.
    await expect(page.getByTestId('status-pill')).toContainText('Replay finished', { timeout: 25_000 });
    const center = page.getByTestId('center-transcript');
    await expect(center.locator('[data-segment-id]')).toHaveCount(3);
    await expect(center.locator('[data-annotation-id="a-seg-5"]')).toHaveAttribute('data-primary', 'happy');
    await expect(center.locator('[data-segment-id="seg-4"] [data-annotation-id]')).toHaveCount(0);

    // History keeps seg-1, seg-2 and the finalized red annotation.
    await page.getByTestId('history-toggle').click();
    const history = page.getByTestId('history');
    await expect(history.locator('[data-segment-id="seg-1"]')).toBeVisible();
    await expect(history.locator('[data-annotation-id="a-seg-2"]')).toHaveAttribute('data-state', 'final');

    // No mic, no WebSocket in Replay.
    const counts = await page.evaluate(() => {
      const w = window as unknown as { __wsOpened: number; __gumCalls: number };
      return { ws: w.__wsOpened, gum: w.__gumCalls };
    });
    expect(counts).toEqual({ ws: 0, gum: 0 });
    if (process.env.E2E_REAL_REPLAY !== '1') {
      expect(requests).toEqual(['/api/v1/replay/manifest', '/api/v1/replay/replay_demo']);
    }

    // Reset clears center and history.
    await page.getByTestId('btn-reset').click();
    await expect(page.locator('[data-segment-id]')).toHaveCount(0);
    await expect(page.getByTestId('btn-start')).toBeEnabled();
  });

  test('G1 invalid replay shows an error and leaves state empty', async ({ page }) => {
    await instrument(page);
    await stubReplay(page);
    await page.route('**/api/v1/replay/**', (route) => {
      const id = new URL(route.request().url()).pathname.split('/').pop();
      if (id === 'manifest') return route.fallback();
      return route.fulfill({
        status: 200,
        headers: { 'Access-Control-Allow-Origin': '*' },
        contentType: 'application/x-ndjson',
        body: '{"schema_version":"1.0","type":"session.status","session_id":"x","seq":1,"issued_at_ms":0,"payload":{"state":"listening","mode":"replay","scribe":"not_required","emotion_model":"not_required","detail":null}}\n{"support":NaN}\n',
      });
    });
    await page.goto('/');
    await page.getByRole('radio', { name: 'Replay' }).click();
    await page.getByTestId('btn-start').click();
    await expect(page.getByTestId('replay-error')).toContainText('Line 2');
    await expect(page.locator('[data-segment-id]')).toHaveCount(0);
  });
});
