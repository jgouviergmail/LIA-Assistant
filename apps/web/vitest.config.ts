import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  // Force development mode for React (required for act() in tests)
  define: {
    'process.env.NODE_ENV': '"test"',
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/__tests__/setup.ts'],
    include: ['src/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}'],
    coverage: {
      reporter: ['text', 'json', 'html'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/**/*.d.ts', 'src/**/__tests__/**', 'src/lib/generated/**'],
      // Ratchet doctrine (same as the backend coverage gate): thresholds are
      // set just under the MEASURED value at the time they were locked, they
      // only ever go UP when new tests land, and they never go down — lowering
      // one to make CI pass is treated as a regression to fix, not a knob.
      // NOTE (verified empirically on vitest 4.1): the global floor is
      // computed over the WHOLE include set — glob-matched files are NOT
      // subtracted from the global pool here.
      thresholds: {
        // Global floor. Measured 2026-07 (435 tests): statements 10.5 /
        // branches 8.67 / functions 7.97 / lines 10.75 — raise as coverage
        // grows.
        statements: 10,
        branches: 8,
        functions: 7,
        lines: 10,
        // Chat state machine — fully covered, keep it that way (2026-07).
        'src/reducers/**/*.ts': {
          statements: 100,
          branches: 100,
          functions: 100,
          lines: 100,
        },
        // SSE handler pipeline — fully covered, incl. backend contract
        // symmetry (see sse-handlers/__tests__/sse-symmetry.test.ts).
        'src/lib/sse-handlers/**/*.ts': {
          statements: 100,
          branches: 100,
          functions: 100,
          lines: 100,
        },
        // Zustand stores — fully covered (2026-07).
        'src/stores/**/*.ts': {
          statements: 100,
          branches: 100,
          functions: 100,
          lines: 100,
        },
        // Chat/voice hooks — measured 2026-07, remaining branches are
        // structurally unreachable in tests (NODE_ENV block compiled to
        // 'test' by `define`, unmount-during-async-setup guards).
        'src/hooks/useChat.ts': {
          statements: 91,
          branches: 88,
          functions: 96,
          lines: 91,
        },
        'src/hooks/useConversation.ts': {
          statements: 98,
          branches: 91,
          functions: 100,
          lines: 98,
        },
        'src/hooks/useVoiceMode.ts': {
          statements: 95,
          branches: 88,
          functions: 76,
          lines: 97,
        },
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
});
