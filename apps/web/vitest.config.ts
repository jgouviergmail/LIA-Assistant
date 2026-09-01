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
        // Global floor — re-measured 2026-08-31 (second pass) after the mouth
        // and the speech bubble (ADR-252: the signed mouth curve and its
        // derived arc, the speaking flap, the comic bubble and its geometric
        // clearance guard):
        // statements 77.41 / branches 72.56 / functions 74.34 / lines 78.01.
        // Raised 75/70/72/75 -> 75/70/72/76 (floor(measured - 2) per axis —
        // lines alone crosses an integer step this time).
        // Global floor — re-measured 2026-08-31 after the expressive-eyes
        // animation rig (ADR-252: the analytic spring integrator, the channel
        // table, the pose/style/script tables, the tape and loop mechanisms,
        // the shared frame clock, the DOM writer, the brow and pupil organs,
        // the matter layer and the CSS boundary guards — ~250 new tests):
        // statements 77.39 / branches 72.52 / functions 74.33 / lines 77.98.
        // Raised 74/70/71/75 -> 75/70/72/75 (floor(measured - 2) per axis —
        // statements and functions cross an integer step this time).
        // Global floor — re-measured 2026-08-30 after the settings group-tone
        // lot (twelve fixed `--color-settings-*` tokens measured across the 15
        // palettes, the tone applied by the overview cards and the rail, and
        // one distinct glyph per section):
        // statements 76.82 / branches 72.08 / functions 73.92 / lines 77.46.
        // Unchanged 74/70/71/75 (floor(measured - 2) per axis — no axis
        // crosses an integer step this time).
        // Global floor — re-measured 2026-08-24 after the native push lot
        // (ADR-246: the shell enrolment path inside useFCMToken, the
        // platform-agnostic push config boundary, and the relay handle the
        // iOS shell registers instead of an FCM token):
        // statements 76.77 / branches 72.08 / functions 73.84 / lines 77.41.
        // Raised 74/69/71/75 -> 74/70/71/75 (floor(measured - 2) per axis —
        // branches alone crosses an integer step this time).
        // Global floor — re-measured 2026-08-22 after the RAG fusion lot
        // (ADR-242: the shared RetrievalSettingsBar extracted from the two
        // injection sections, the recalibrated relevance tiers, the threshold
        // tick wired onto every score bar and the RAG section's settings /
        // empty-result contract):
        // statements 76.49 / branches 71.65 / functions 73.55 / lines 77.15.
        // Unchanged 74/69/71/75 (floor(measured - 2) per axis — no axis crosses
        // an integer step this time).
        // Global floor — re-measured 2026-08-20 after the prod-log remediation
        // lot (SSE superseded handling in useNotifications + BroadcastProvider
        // with visibility-driven resume, the live-demo CTA telemetry):
        // statements 75.71 / branches 70.98 / functions 72.62 / lines 76.35.
        // Unchanged 73/68/70/74 (floor(measured - 2) per axis — no axis
        // crosses an integer step this time).
        // Global floor — re-measured 2026-08-19 after evolution-program Lots
        // 1-4 (ADR-234..237: the activity timeline feed + hook, the habit
        // streak block, the initiative-motivation reducer branches, the
        // psyche-tinted typing acknowledgment):
        // statements 75.57 / branches 70.89 / functions 72.50 / lines 76.19.
        // Unchanged 73/68/70/74 (floor(measured - 2) per axis — no axis
        // crosses an integer step this time).
        // Global floor — re-measured 2026-08-19 after the tabular import/export
        // lot (ADR-228: the workbook hook, the import state machine and the
        // preview dialog with its issue/diff/apply oracles) plus the browser
        // journey of the whole round trip:
        // statements 75.53 / branches 70.81 / functions 72.45 / lines 76.17.
        // Raised 72/68/69/73 -> 73/68/70/74 (floor(measured - 2) per axis —
        // branches alone does not cross an integer step this time).
        // Global floor — re-measured 2026-08-18 after the capability-map /
        // settings-hub lot (ADR-229: the shared capability↔section table and
        // its derived reverse, the hub status line with its four silences,
        // the landing release band and the shared changelog key builders,
        // plus the single-form SettingsSection contract):
        // statements 74.89 / branches 70.51 / functions 71.54 / lines 75.53.
        // Raised 72/68/68/72 -> 72/68/69/73 (floor(measured - 2) per axis —
        // functions and lines cross an integer step this time).
        // Global floor — re-measured 2026-08-17 after the time-slot LLM
        // pricing lot (ADR-223: the slot editor and its pure helpers —
        // validation mirror, payload builder, UTC-offset label — plus the
        // windowed-tariff branches of the pricing modal):
        // statements 74.16 / branches 70.15 / functions 70.84 / lines 74.76.
        // Raised 71/67/68/72 -> 72/68/68/72 (floor(measured - 2) per axis —
        // statements and branches cross an integer step this time).
        // Previous re-measure 2026-08-07 after the demonstrator's
        // security audit and the removal of the legacy live showroom (the
        // server-side proxy routes, its adapter and its hook: code the suite
        // covered thinly and that no longer exists):
        // statements 73.77 / branches 69.83 / functions 70.33 / lines 74.41.
        // Raised 71/67/67/71 -> 71/67/68/72 (floor(measured - 2) per axis —
        // functions and lines cross an integer step this time).
        // Previous re-measure 2026-08-05 after the production-log
        // remediation (the dashboard shell no longer mounts for an account
        // awaiting activation, which is what kept two EventSources retrying a
        // 403 five times each):
        // statements 73.33 / branches 69.4 / functions 69.5 / lines 73.93.
        // Raised 70/67/67/71 -> 71/67/67/71 (floor(measured - 2) per axis —
        // only statements crosses an integer step this time).
        // Previous re-measure 2026-08-05 after the intent-replay lot
        // (ADR-210: the consumed-intent ledger, the replay branch of
        // useDeepLinkParams, the extracted resolveInitialMessage, the
        // UsageStatistics disclosure test):
        // statements 72.79 / branches 69.12 / functions 69.11 / lines 73.35.
        // Raised 70/66/66/71 -> 70/67/67/71 (floor(measured - 2) per axis —
        // only branches and functions cross an integer step this time).
        // Previous re-measure 2026-08-05 after the debug-panel
        // overhaul (ADR-209: the tone foundation and its node families, the
        // shared ScoreBar/legend, the 30 execution-ordered sections, the
        // presence/anomaly derivations, the entry header and pipeline strip,
        // and the schema detector):
        // statements 72.66 / branches 68.76 / functions 68.98 / lines 73.22.
        // Raised 68/62/64/69 -> 70/66/66/71 (floor(measured - 2) on every
        // axis — the ~110 debug-panel tests moved all four floors at once).
        // Previous re-measure 2026-08-05 after the design-system
        // consistency lot (the shared field plumbing behind `Input`/`Textarea`,
        // the localised spinner, the decorative skeletons, the shared
        // `EmptyState` and its seven call sites, and the focus/`aria-current`
        // fix on the language and timezone pickers):
        // statements 70.77 / branches 64.91 / functions 66.61 / lines 71.35.
        // 68/62/64/69 HOLDS — every axis gained ground, none crosses an integer
        // step while keeping the 2-point margin, so nothing to raise.
        // Previous re-measure 2026-08-04 after the visual-consistency lot
        // (`status-tone` and its three call sites, the design-system Button on
        // the relation and hub actions, the tinted hub pill, the coloured
        // contact icons and the clickable memories):
        // statements 70.76 / branches 64.88 / functions 66.60 / lines 71.33.
        // 68/62/64/69 HOLDS — branches gained again but no axis crosses an
        // integer step while keeping the 2-point margin.
        // Previous re-measure 2026-08-04 after the hub-counts lot (the
        // aggregated badge read and its gate-keeper, the two repository
        // counters now delegating to ONE filter, the peer avatar and the two
        // mobile-withheld blocks):
        // statements 70.76 / branches 64.86 / functions 66.60 / lines 71.33.
        // 68/62/64/69 HOLDS — every axis gained ground but none crosses an
        // integer step while keeping the 2-point margin.
        // Previous re-measure 2026-08-04 (the capability constellation:
        // the angular figure, the deterministic backdrop, the token-scope
        // guard that would have caught the black SVG, and the "no invented
        // tally" helper shared by the chart and the list):
        // statements 70.72 / branches 64.78 / functions 66.53 / lines 71.29.
        // 68/62/64/69 HOLDS — every axis gained ground but none crosses an
        // integer step while keeping the 2-point margin, so nothing to raise.
        // Previous re-measure 2026-08-03 after the review pass (the
        // dependency publication, the atomic results aggregate, ownership at
        // the service layer, the localized untitled event, the surrogate-safe
        // trim, the unknown-priority and unknown-suggestion guards, and their
        // two backend-symmetry tests):
        // statements 70.42 / branches 64.31 / functions 66.26 / lines 71.01.
        // Raised lines 68 -> 69 (floor(measured - 2)); the other three hold —
        // no integer step admits the 2-point margin there yet.
        // Previous re-measure 2026-08-03 (ADR-196→199: the eleven
        // proactivity switches and the history behind them, the grounded
        // starter rail and the results block, occurrence rendering in the
        // routine's own clock, the device-scoped haptic preference, reminder
        // cancellation, and the gallery keyboard/lightbox contract):
        // statements 70.38 / branches 64.26 / functions 66.20 / lines 70.97.
        // Raised 68/61/63/68 -> 68/62/64/68 (floor(measured - 2); statements
        // and lines hold — no integer step admits the 2-point margin there).
        // Previous re-measure 2026-08-01 night (ADR-193: the merge panel
        // and its undo list, the merge/split hook and its refusal paths, plus
        // the touch-target fixes):
        // statements 70.14 / branches 63.89 / functions 65.77 / lines 70.73.
        // 68/61/63/68 HOLDS — every axis gained ground but none crosses an
        // integer step while keeping the 2-point margin, so nothing to raise.
        // The gains are locked per-directory instead, on the relations glob.
        // Previous re-measure 2026-08-01 late (ADR-190: the full contact
        // card and its date/label rendering, the 360° scope selector and its
        // draft/commit hook, plus the header-button removal):
        // statements 70.02 / branches 63.59 / functions 65.57 / lines 70.61.
        // Raised 67/61/63/68 -> 68/61/63/68 (floor(measured - 2); branches,
        // functions and lines hold — no integer step admits the 2-point margin
        // there yet).
        // Previous re-measure 2026-08-01 (landing gallery: the shared
        // LandingCarousel with its keyboard/swipe/live-region contract, the two
        // tab inventories, the disclosure open by default, Tabs.defaultTabId):
        // statements 69.98 / branches 63.57 / functions 65.55 / lines 70.57.
        // Raised 67/61/62/68 -> 67/61/63/68 (floor(measured - 2); statements,
        // branches and lines hold — no integer step admits the 2-point margin
        // there yet).
        // Previous re-measure 2026-07-31 late (Bloc B + Bloc C:
        // discovery by address, the provider-backed 360° sections, plus the
        // refetch/focus regressions and their guards):
        // statements 69.58 / branches 63.20 / functions 64.90 / lines 70.18.
        // Raised 67/60/62/68 -> 67/61/62/68 (floor(measured - 2); statements,
        // functions and lines hold — no integer step admits the 2-point
        // margin there yet).
        // Previous re-measure 2026-07-31 (Relations CRM enrichment,
        // ADR-185: relayed peer messages, exact aggregate counts, progressive
        // disclosure, the LIA connection block, dormancy + sort/filters, quick
        // actions, plus the useRelationDetail hook tests):
        // statements 69.49 / branches 62.95 / functions 64.77 / lines 70.10.
        // Raised 67/60/62/67 -> 67/60/62/68 (floor(measured - 2); statements,
        // branches and functions hold — no integer step admits the 2-point
        // margin there yet).
        // Previous re-measure 2026-07-30 (LIA Cosmos swap: `/` and the
        // whole public space carry the identity, preview routes deleted, page
        // tests migrated to the real routes + app adjustments wave):
        // statements 69.25 / branches 62.75 / functions 64.43 / lines 69.86.
        // Raised 66/60/61/67 -> 67/60/62/67 (floor(measured - 2); branches
        // and lines hold — no integer step admits the 2-point margin there).
        // Previous re-measure 2026-07-30 (LIA Cosmos Lot A: cosmic
        // primitives, planetarium, pinned day, count-up, preview pages):
        // statements 68.58 / branches 62.38 / functions 63.65 / lines 69.17.
        // Raised 65/60/60/66 -> 66/60/61/67 (floor(measured - 2); branches
        // hold — no integer step admits the 2-point margin there yet).
        // Previous re-measure 2026-07-30 (peers Lot 7: chat quick
        // actions, tinted bubbles, own-name block, discovery status badge):
        // statements 67.94 / branches 62.07 / functions 62.90 / lines 68.51.
        // Previous re-measure 2026-07-29 late (339 files / 4,201 tests,
        // peers program Lot 2: hook + 7 section components at 98.7/86.9/100/100):
        // statements 67.85 / branches 62.01 / functions 62.79 / lines 68.42.
        // Branches raised 59 → 60 (floor(measured - 2)); the other three stay —
        // the 2-point margin doctrine does not admit another integer step yet.
        // Previous re-measure same day (329 files / 4,072 tests):
        // statements 67.60 / branches 61.82 / functions 62.46 / lines 68.16.
        // Raised to 65/59/60/66 for the ADR-177 rich-HTML wave (sanitize
        // vocabulary, rich-components rendering, html-plain-text flattener,
        // message-clipboard dual-flavor, search-highlight ligature guard) —
        // floor(measured - 2) per the doctrine, >= 1.8 points of margin held.
        // Previous lock 2026-07-28 (296 files / 3,491 tests): 66.40 / 60.13 /
        // 60.52 / 66.96, floors at 64/58/58/65.
        // Raised twice in one pass: first for the API-error-contract wave
        // (api-error, api-server, settings server actions, the i18n middleware,
        // the connector hooks — was 62/56/56/62), then for the localized wind
        // card plus ADR-152, which took 861 lines of orphan code out of the
        // denominator. Set just under, raise as coverage grows, NEVER lower.
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
        // Re-locked 2026-08-20 (473 files / 6,012 tests) after the
        // expressive-eyes waves (engine matrix + idle life + performances +
        // touch toolbar): measured 76.20 / 71.39 / 73.20 / 76.85 →
        // statements joins branches and functions one point up
        // (floor(measured - 2)); lines already sits at its doctrine floor.
        // Global floor — re-measured 2026-08-21 after the eyes liveliness +
        // lid-system lots (transition grammar with min-hold and masked
        // three-beat, the reading line, mood-shift/wonder/wake beats, the
        // per-family breathing/blink channels, and the curved clip lids):
        // statements 76.47 / branches 71.60 / functions 73.52 / lines 77.13.
        // Raised 74/69/71/74 -> 74/69/71/75 (floor(measured - 2) per axis —
        // lines alone crosses an integer step this time).
        statements: 75,
        branches: 70,
        functions: 72,
        lines: 76,
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
        // The expressive-eyes animation rig (ADR-252). Measured 2026-08-31:
        // `components/eyes` 95.24 / 88.31 / 97.29 / 97.62 and its `rig`
        // subtree 99.78 / 98.11 / 100 / 100. The rig is pure and clock-driven,
        // so its behaviour is testable frame by frame — which is exactly why
        // it must stay near-total: the motion IS the feature, and a regression
        // there is invisible to every other gate.
        'src/components/eyes/**/*.{ts,tsx}': {
          statements: 93,
          branches: 86,
          functions: 95,
          lines: 95,
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
        // CRM Relations components — the 360° card, its provider sections, the
        // scope selector and the merge panel. Measured 2026-08-01 on the glob
        // itself: statements 93.3 / branches 93.2 / functions 94.9 / lines 94.2.
        // Locked here because this surface carries decisions a user cannot undo
        // by reloading (a merge) and claims they must be able to trust (exact
        // counts, who someone is). Set just under, never lower.
        'src/components/relations/**/*.tsx': {
          statements: 91,
          branches: 91,
          functions: 92,
          lines: 92,
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
        // auth pages, the logout that must land even when the API refuses, the
        // reference-stable refresh, and — since the shells — the native
        // handoff and the sign-in that must leave for the system browser
        // instead of navigating a WebView Google refuses. Measured
        // 100 / 94.11 / 100 / 100; floor raised from 88 with the branch
        // coverage those paths added.
        // The one door every OAuth flow leaves through — connectors, MCP, bulk
        // connect, reconnection, sign-in. It guards a navigation primitive
        // against `javascript:` URLs (SEC-002) AND decides whether the URL goes
        // to the system browser instead of the WebView (ADR-246). Two
        // load-bearing decisions in eleven lines, and a regression in either is
        // invisible until it is a security hole or eight broken flows.
        // Measured 100 / 100 / 100 / 100 — locked there.
        'src/lib/safe-navigation.ts': {
          statements: 100,
          branches: 100,
          functions: 100,
          lines: 100,
        },
        // The native-shell boundary — the only code in the bundle that changes
        // behaviour based on WHERE it runs, and the hardest to notice breaking:
        // nothing in a browser exercises it, and nothing in CI runs a WebView.
        // Measured 97.22 / 91.66 / 100 / 100 (the one uncovered branch is the
        // SSR guard, which jsdom cannot enter).
        'src/lib/native/**/*.ts': {
          statements: 95,
          branches: 89,
          functions: 98,
          lines: 98,
        },
        'src/lib/auth.tsx': {
          statements: 98,
          branches: 92,
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
