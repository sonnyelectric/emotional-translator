// Screenshot helper for the visual redesign. Needs scripts/demo_replay.sh running.
// Usage: node scripts/redesign_shots.mjs <prefix> [extra]   e.g. before | after
// extra=1 also captures the Okabe-Ito palette and reduced-motion variants.
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';

const prefix = process.argv[2] ?? 'after';
const extra = process.argv[3] === '1';
const out = new URL('../../docs/screenshots/redesign/', import.meta.url).pathname;
mkdirSync(out, { recursive: true });
const URL_ = process.env.APP_URL ?? 'http://localhost:5173';

const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || 'chrome' });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();

async function fresh() {
  await page.goto(URL_);
  await page.evaluate(() => localStorage.clear());
  await page.reload();
}

await fresh();
await page.waitForTimeout(600);
await page.screenshot({ path: `${out}${prefix}-live-empty.png` });

await page.getByRole('radio', { name: 'Replay' }).click();
await page.getByTestId('btn-start').click();
await page.getByTestId('status-pill').filter({ hasText: 'Replay finished' }).waitFor({ timeout: 40_000 });
await page.waitForTimeout(1200);
await page.screenshot({ path: `${out}${prefix}-main.png` });

await page.locator('[data-annotation-id="a-seg-5"]').first().click();
await page.waitForTimeout(500);
await page.screenshot({ path: `${out}${prefix}-inspector.png` });
await page.keyboard.press('Escape');

await page.getByRole('button', { name: 'Settings' }).click();
await page.waitForTimeout(400);
await page.screenshot({ path: `${out}${prefix}-settings.png` });

if (extra) {
  await page.getByLabel('Color-blind safe').check();
  await page.getByRole('button', { name: 'Settings' }).click();
  await page.getByTestId('history-toggle').click();
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${out}${prefix}-cvd.png` });
  const rm = await page.evaluate(() => document.querySelector('.app')?.getAttribute('data-reduced-motion'));
  console.log('data-reduced-motion =', rm);
}
await browser.close();
console.log('saved', prefix);
