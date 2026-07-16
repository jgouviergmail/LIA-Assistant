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
    // Under heavy parallel load (50+ jsdom files) a fork worker occasionally
    // needs more than the 10s default to tear down its jsdom environment,
    // producing an intermittent "Timeout terminating forks worker" warning
    // (tests still pass). The teardown is slow, not stuck — give it margin so
    // the warning never turns into a flaky CI signal.
    teardownTimeout: 30000,
    include: ['src/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}'],
    coverage: {
      reporter: ['text', 'json', 'html'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.d.ts',
        'src/**/__tests__/**',
        'src/lib/generated/**',
        // Trivial shadcn/ui primitives: thin re-exports of a Radix primitive or
        // a single HTML element with `cn()` class merging and no branching,
        // state, derived data or own interaction handlers. Testing them asserts
        // Radix behaviour or className strings — coverage theatre — so they are
        // out of the measured perimeter (chantier couverture frontend, Lot 0).
        // Primitives that DO carry real logic/variants (button, badge, card,
        // status-badge, alert, info-box, avatar, pagination, search-input,
        // select, image-lightbox, inline-place-carousel, loading-spinner,
        // animated-emoji) stay in and are tested.
        'src/components/ui/separator.tsx',
        'src/components/ui/slider.tsx',
        'src/components/ui/switch.tsx',
        'src/components/ui/label.tsx',
        'src/components/ui/tooltip.tsx',
        'src/components/ui/accordion.tsx',
        'src/components/ui/tabs.tsx',
        'src/components/ui/dialog.tsx',
        'src/components/ui/alert-dialog.tsx',
        'src/components/ui/dropdown-menu.tsx',
        'src/components/ui/input.tsx',
        'src/components/ui/textarea.tsx',
        'src/components/ui/skeleton.tsx',
        'src/components/ui/toaster.tsx',
      ],
      // Ratchet doctrine (same as the backend coverage gate): thresholds are
      // set just under the MEASURED value at the time they were locked, they
      // only ever go UP when new tests land, and they never go down — lowering
      // one to make CI pass is treated as a regression to fix, not a knob.
      // NOTE (verified empirically on vitest 4.1): the global floor is
      // computed over the WHOLE include set — glob-matched files are NOT
      // subtracted from the global pool here.
      thresholds: {
        // Global floor. Measured 2026-07-15 after the risk-first hook wave
        // (audit F010), the component coverage chantier Lots 1-4, the breadth
        // waves, AND the F010 risk-first extension (F057 builder remediation +
        // settings forms, connector credential forms, voice/geolocation):
        // statements 35.4 / branches 33.54 / functions 29.25 / lines 35.83 —
        // set just under, raise as coverage grows, never lower.
        statements: 35,
        branches: 33,
        functions: 29,
        lines: 35,
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
        // UI primitives with real logic/variants — chantier couverture frontend
        // Lot 1 (2026-07-15). Measured over the 14 non-trivial components (the
        // trivial re-exports are in coverage.exclude): statements 90.2 /
        // branches 85.7 / functions 86.2 / lines 90.6. Set just under; raise as
        // more UI behaviour is pinned, never lower.
        'src/components/ui/**/*.tsx': {
          statements: 88,
          branches: 83,
          functions: 84,
          lines: 88,
        },
        // Connector components (settings/connectors/*.tsx) — F010 risk-first
        // extension: connector cards, preference dropdown and the credential
        // forms (Apple, Hue, API key, telephony). The .ts provider hooks are
        // mocked out of these component tests and sit outside this .tsx glob.
        // Set just under; raise as LocationSettings / UserConnectorsSection
        // land, never lower.
        'src/components/settings/connectors/**/*.tsx': {
          statements: 60,
          branches: 50,
          functions: 46,
          lines: 60,
        },
        // Voice components — F010 risk-first extension (VoiceOverlay +
        // VoiceModeBadge state machine / long-press). Measured 71.7 / 65.6 /
        // 88.2 / 71.7; set just under, never lower.
        'src/components/voice/**/*.tsx': {
          statements: 68,
          branches: 62,
          functions: 82,
          lines: 68,
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
