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
    // Same reasoning, one level down. Vitest's per-test default is 5 s, which
    // is a framework default nobody here calibrated. The settings mega-forms
    // drive real `userEvent` typing on controlled inputs (~29 ms per keystroke,
    // measured), and under full-suite parallelism WITH coverage instrumentation
    // that stretches roughly 5x: the heaviest creation test ran 1.0 s alone and
    // timed out past 5 s in the full run — a green test reported as a failure.
    // Measured worst case across the suite is ~3.3 s, so 15 s keeps ~4x headroom
    // while still catching a genuinely hung test quickly. Raise this only from a
    // fresh measurement, never to silence one slow test.
    testTimeout: 15000,
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
        // Global floor — measured 2026-07-19:
        //   statements 60.46 / branches 54.80 / functions 54.49 / lines 60.91
        // Set just under, raise as coverage grows, NEVER lower.
        //
        // How it got here (audit F010, chantier "couverture par le risque"):
        // the hook wave and component Lots 1-4, then the F057 builder
        // remediation, then the admin sections, the settings mega-forms taken
        // past their loading/empty states, the chat/companion/connector-hook
        // wave, the data-layer wave that stopped mocking the hooks out, and
        // finally the voice/push chain (WS transport, push-to-talk state
        // machine, FCM enrolment). Deliberately NOT covered here and left to
        // other lanes: App Router pages (hermetic E2E) and the WASM/Web-Audio
        // modules `sherpaKws` / `audio-queue`, which jsdom cannot simulate
        // without the test degenerating into a test of its own mocks.
        statements: 60,
        branches: 54,
        functions: 54,
        lines: 60,
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
        // Lot 1 (2026-07-15), re-measured 2026-07-19 after the lightbox focus
        // trap. Measured over the 14 non-trivial components (the trivial
        // re-exports are in coverage.exclude): statements 90.4 / branches 86.3 /
        // functions 86.2 / lines 91.3. Set just under; raise as more UI
        // behaviour is pinned, never lower.
        'src/components/ui/**/*.tsx': {
          statements: 88,
          branches: 84,
          functions: 84,
          lines: 89,
        },
        // Connector components (settings/connectors/*.tsx) — F010 risk-first
        // extension: connector cards, preference dropdown, the credential forms
        // (Apple, Hue, API key, telephony) and LocationSettings.
        //
        // These numbers used to come from the WHOLE directory aggregate, which
        // still carried the then-uncovered .ts provider hooks — a floor set
        // from the wrong population, 14.7 points below what this glob actually
        // measured on functions. Now that the hooks carry their own lock below,
        // this is measured on the .tsx subset itself: 86.0 / 75.6 / 72.7 / 86.8.
        // Set just under, never lower.
        'src/components/settings/connectors/**/*.tsx': {
          statements: 84,
          branches: 73,
          functions: 70,
          lines: 84,
        },
        // Connector provider hooks — F010 risk-first extension. These were
        // systematically mocked out by the component tests (three of them sat
        // at 0 %): the Hue pairing state machine, the bulk-OAuth queue that
        // survives a redirect, and the optimistic preference save + rollback
        // are now driven directly. Measured 83.9 / 72.1 / 83.7 / 84.1; set just
        // under, never lower.
        'src/components/settings/connectors/hooks/**/*.ts': {
          statements: 82,
          branches: 70,
          functions: 80,
          lines: 82,
        },
        // Companion presence — F010 risk-first extension: the floating avatar
        // owns an SSE subscription and a poll that MUST go quiet off-page.
        // Measured 98.5 / 90.9 / 94.1 / 100; set just under, never lower.
        'src/components/companion/**/*.tsx': {
          statements: 96,
          branches: 88,
          functions: 92,
          lines: 98,
        },
        // Voice components — F010 risk-first extension (VoiceOverlay +
        // VoiceModeBadge state machine / long-press). Measured 71.8 / 65.6 /
        // 88.2 / 71.8; set just under, never lower.
        'src/components/voice/**/*.tsx': {
          statements: 68,
          branches: 62,
          functions: 86,
          lines: 68,
        },
        // FAQ page — chantier couverture Lot 5. Driven by a controlled
        // dictionary (the global i18n stub echoes keys, which would make every
        // assertion vacuous). Measured 90.7 / 95.0 / 85.2 / 91.5.
        'src/components/faq/**/*.tsx': {
          statements: 88,
          branches: 92,
          functions: 83,
          lines: 89,
        },
        // Chat SSE transport — the whole conversation rides on it, so it is
        // driven for real over a stubbed fetch (status→i18n mapping, frame
        // reassembly, cancellation). Measured 94.9 / 84.9 / 100 / 94.9.
        'src/lib/api/chat.ts': {
          statements: 93,
          branches: 83,
          functions: 98,
          lines: 93,
        },
        // Session boundary (BFF): the mount-time check skipped on the public
        // auth pages, the logout that must land even when the API refuses, and
        // the reference-stable refresh. Measured 100 / 90 / 100 / 100.
        'src/lib/auth.tsx': {
          statements: 98,
          branches: 88,
          functions: 98,
          lines: 98,
        },
        // Admin broadcast provider — three arrival doors (unread fetch, SSE,
        // FCM) that must produce one modal per announcement, plus the
        // cross-tab sync. Measured 100 / 89.6 / 92.6 / 100.
        'src/lib/broadcast.tsx': {
          statements: 98,
          branches: 87,
          functions: 90,
          lines: 98,
        },
        // Voice WebSocket transport — ticket (BFF), backoff that only fires on
        // an unexpected close, and a budget that resets on a successful retry.
        // Measured 99 / 84.4 / 95.6 / 99; set just under, never lower.
        'src/lib/voice-input-service.ts': {
          statements: 98,
          branches: 83,
          functions: 95,
          lines: 98,
        },
        // Attachment pipeline — validation, XHR progress, and the abort +
        // Object-URL revocation discipline. Measured 100 / 83.9 / 100 / 100.
        'src/hooks/useFileUpload.ts': {
          statements: 98,
          branches: 82,
          functions: 98,
          lines: 98,
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
