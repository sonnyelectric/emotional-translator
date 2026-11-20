import { defineConfig, devices } from '@playwright/test';

// E2E_PORT: Vite port for the test server (default 5174 so it never collides with a running
// 5173 dev server). PW_CHANNEL=chrome uses an installed Google Chrome instead of the
// downloaded Chromium (`npm run install:browsers`).
// E2E_REAL_REPLAY=1 targets the real local backend instead of stubbed replay responses.
const port = Number(process.env.E2E_PORT ?? 5174);

export default defineConfig({
  testDir: './tests',
  testMatch: /.*\.spec\.ts$/,
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: `http://localhost:${port}`,
    viewport: { width: 1280, height: 720 },
    trace: 'off',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1280, height: 720 },
        channel: process.env.PW_CHANNEL || undefined,
        permissions: ['microphone'],
        launchOptions: {
          args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', '--autoplay-policy=no-user-gesture-required'],
        },
      },
    },
  ],
  webServer: {
    command: `npx vite --host localhost --port ${port} --strictPort`,
    url: `http://localhost:${port}`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
