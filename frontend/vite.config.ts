/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

const sharedDir = fileURLToPath(new URL('../shared', import.meta.url));

// `vite build --mode replay` (npm run build:replay) produces a backend-free static
// build that bundles shared/fixtures and always shows the REPLAY banner (PLAN D10).
export default defineConfig(({ mode }) => {
  const staticReplay = mode === 'replay';
  return {
    plugins: [react()],
    base: staticReplay ? './' : '/',
    define: {
      __STATIC_REPLAY__: JSON.stringify(staticReplay),
    },
    server: {
      host: 'localhost',
      port: 5173,
      fs: { allow: ['.', sharedDir] },
    },
    preview: {
      host: 'localhost',
    },
    worker: { format: 'es' as const },
    build: {
      outDir: staticReplay ? 'dist-replay' : 'dist',
      emptyOutDir: true,
      target: 'es2022',
    },
    test: {
      environment: 'node',
      include: ['tests/**/*.test.ts', 'src/**/*.test.ts'],
    },
  };
});
