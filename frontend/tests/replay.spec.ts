import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { instrument, stubReplay } from './e2e-helpers';

const MANIFEST_PATH = fileURLToPath(new URL('../../shared/fixtures/manifest.json', import.meta.url));

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
    // One continuous transcript: every segment stays in the scrolling stage, newest in view.
    await expect(center.locator('[data-segment-id]')).toHaveCount(5);
    await expect(center.locator('[data-annotation-id="a-seg-5"]')).toHaveAttribute('data-primary', 'happy');
    await expect(center.locator('[data-segment-id="seg-4"] [data-annotation-id]')).toHaveCount(0);
    await expect(center.locator('[data-segment-id="seg-5"]')).toBeInViewport();

    // Older content is kept: scroll back up to seg-1 and the finalized red annotation.
    await center.locator('[data-segment-id="seg-1"]').scrollIntoViewIfNeeded();
    await expect(center.locator('[data-segment-id="seg-1"]')).toBeVisible();
    await expect(center.locator('[data-annotation-id="a-seg-2"]')).toHaveAttribute('data-state', 'finalized');
    await expect(page.getByTestId('jump-latest')).toBeVisible();
    await page.getByTestId('jump-latest').click();
    await expect(center.locator('[data-segment-id="seg-5"]')).toBeInViewport();

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

test.describe('replay provenance labels', () => {
  test('synthetic fixture never claims saved model output', async ({ page }) => {
    await instrument(page);
    await stubReplay(page);
    await page.goto('/');
    await page.getByRole('radio', { name: 'Replay' }).click();
    await page.getByTestId('btn-start').click();
    await expect(page.getByTestId('replay-provenance')).toContainText('Synthetic example (hand-written, not model output)');
    const banner = await page.getByTestId('replay-banner').innerText();
    expect(banner).not.toMatch(/saved result|recorded/i);
    await expect(page.getByTestId('cue-footnote')).toContainText('Synthetic example (hand-written, not model output)');
    await expect(page.getByTestId('cue-footnote')).not.toContainText('emotion2vec');
    await expect(page.getByText('Saved result')).toHaveCount(0);
  });

  test('a recorded_result entry is labelled as a recorded live session', async ({ page }) => {
    // UI-labelling test only: the manifest entry is stubbed; it reuses a synthetic file's
    // events so nothing here is presented as real model output outside this test.
    const manifest = JSON.parse(readFileSync(MANIFEST_PATH, 'utf8'));
    const anger = manifest.fixtures.find((f: { id: string }) => f.id === 'replay_anger_sad');
    manifest.fixtures = [
      {
        ...anger,
        case_name: 'Recorded live session, 2026-11-20',
        provenance: 'recorded_result',
        provenance_detail: 'recorded live session (text, timestamps, scores; no audio)',
        recorded_on: '2026-11-20',
      },
    ];
    manifest.default_fixture = anger.id;
    await instrument(page);
    await stubReplay(page, [], manifest);
    await page.goto('/');
    await page.getByRole('radio', { name: 'Replay' }).click();
    await page.getByTestId('btn-start').click();
    await expect(page.getByTestId('replay-provenance')).toContainText(
      'Recorded live session, 2026-11-20 (text, timestamps, scores; no audio)',
    );
    await expect(page.getByTestId('cue-footnote')).toContainText('Recorded live session');
    await expect(page.getByTestId('replay-provenance')).not.toContainText('Synthetic');
  });
});
