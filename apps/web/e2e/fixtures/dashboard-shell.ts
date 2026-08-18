/**
 * Common hermetic mocks for the authenticated dashboard SHELL.
 *
 * The dashboard layout and its always-mounted widgets (personality selector,
 * connector-health alert, psyche companion, usage tile, app config, voice
 * ticket, RAG-space pickers) fire these calls on EVERY authenticated page.
 * Without them each one hits the 501 catch-all — noisy console errors on
 * every spec and a drift trap (a new shell widget silently degrades every
 * journey). They are installed by the `authenticate` fixture, BEFORE any
 * spec-specific mock, so specs override them freely (Playwright routes are
 * LIFO — last registered wins). The catch-all stays: any endpoint NOT listed
 * here and not mocked by the spec is still a loud 501 failure.
 *
 * Shapes mirror the frontend contracts exactly (see the type imports named in
 * each entry) — payloads are minimal but type-correct so components render
 * their real "empty/nominal" states, never a parse error.
 */
import type { MockRoute } from './api-mock';

/** Mirrors `AppConfig` (src/hooks/useAppConfig.ts). */
const appConfig = {
  sse: { heartbeat_interval_seconds: 30 },
  rate_limits: { enabled: false, per_minute: 60, burst: 10 },
  i18n: { supported_languages: ['en', 'fr', 'de', 'es', 'it', 'zh'], default_language: 'en' },
  features: {
    tool_approval_enabled: false,
    attachments_enabled: true,
    rag_spaces_enabled: true,
    rag_spaces_embedding_model: 'text-embedding-3-small',
  },
  api_version: 'v1',
};

/** Mirrors `PsycheState` (src/types/psyche.ts) — calm nominal state. */
const psycheState = {
  id: '00000000-0000-4000-8000-0000000000ps',
  user_id: '00000000-0000-4000-8000-000000000001',
  trait_openness: 0.6,
  trait_conscientiousness: 0.6,
  trait_extraversion: 0.5,
  trait_agreeableness: 0.7,
  trait_neuroticism: 0.3,
  mood_pleasure: 0.2,
  mood_arousal: 0.0,
  mood_dominance: 0.1,
  mood_label: 'neutral',
  mood_color: '#8b9dc3',
  active_emotions: [],
  relationship_stage: 'ORIENTATION',
  relationship_depth: 0.1,
  relationship_warmth_active: 0.2,
  relationship_trust: 0.2,
  relationship_interaction_count: 3,
  drive_curiosity: 0.5,
  drive_engagement: 0.5,
  self_efficacy: {},
  created_at: '2026-07-01T09:00:00Z',
  updated_at: '2026-07-15T10:00:00Z',
};

/** Mirrors `LimitDetail` (src/types/usage-limits.ts). */
const unlimited = { current: 0, limit: null, usage_pct: null, exceeded: false };

export const dashboardShellMocks: MockRoute[] = [
  // App config (src/hooks/useAppConfig.ts) — chat page feature flags.
  { url: '**/api/v1/config', json: appConfig },

  // Personality selector (src/lib/api/personality.ts).
  {
    url: '**/api/v1/personalities',
    json: {
      personalities: [
        {
          id: '00000000-0000-4000-8000-0000000000pe',
          code: 'default',
          emoji: '🤖',
          is_default: true,
          title: 'Default',
          description: 'Balanced assistant personality',
        },
      ],
      count: 1,
    },
  },
  { url: '**/api/v1/personalities/current', json: { personality_id: null, personality: null } },

  // Connector health alert (src/hooks/useConnectorHealth.ts) — healthy, no polling churn.
  {
    url: '**/api/v1/connectors/health/settings',
    json: { polling_interval_ms: 300_000, critical_cooldown_ms: 86_400_000 },
  },
  {
    url: '**/api/v1/connectors/health',
    json: {
      connectors: [],
      has_issues: false,
      critical_count: 0,
      warning_count: 0,
      checked_at: '2026-07-15T10:00:00Z',
    },
  },

  // Psyche companion presence (src/stores/psycheStore.ts).
  { url: '**/api/v1/psyche/state', json: psycheState },

  // Usage limits tile (src/types/usage-limits.ts → UserUsageLimitResponse).
  {
    url: '**/api/v1/usage-limits/me',
    json: {
      status: 'ok',
      is_blocked: false,
      blocked_reason: null,
      cycle_tokens: unlimited,
      cycle_messages: unlimited,
      cycle_cost: unlimited,
      absolute_tokens: unlimited,
      absolute_messages: unlimited,
      absolute_cost: unlimited,
      cycle_start: '2026-07-01T00:00:00Z',
      cycle_end: '2026-08-01T00:00:00Z',
    },
  },

  // Voice input ticket (src/lib/voice-input-service.ts). Deliberately a clean
  // 403 — NOT a valid ticket: a granted ticket makes the service open a real
  // `wss://…/api/v1/voice/ws/audio` connection (Playwright routes do not
  // intercept WebSockets), which retry-storms the dev server with errors for
  // the rest of the run. A 403 is a declared, expected "voice unavailable"
  // outcome: the service logs and stops, no socket, no 501 noise.
  {
    url: '**/api/v1/voice/ticket',
    method: 'POST',
    status: 403,
    json: { detail: 'voice disabled in hermetic E2E' },
  },

  // RAG space pickers outside the spaces pages (empty catalogue). `*` does not
  // cross `/`, so `/rag-spaces/<id>` stays unmocked here (spec concern).
  { url: '**/api/v1/rag-spaces*', json: { spaces: [], total: 0 } },

  // Capability map (src/hooks/useCapabilities.ts). Read by the constellation
  // page AND, since the settings hub gained its status lines, by the settings
  // landing — one of the most visited authenticated screens. Two nodes on
  // purpose: one live WITH a tally and one dormant, so both states of the
  // status line are on screen for the axe scans and the smoke assertions.
  {
    url: '**/api/v1/capabilities',
    json: {
      nodes: [
        { key: 'memory', active: true, detail: 12 },
        { key: 'connectors', active: false, detail: 0 },
      ],
      live: 1,
      total: 2,
    },
  },
];

/**
 * A briefing bundle with all NINE sections resolved and empty.
 *
 * `CardsBundle` (apps/api → domains/briefing/schemas.py) declares all nine as
 * REQUIRED, so the backend cannot omit one. A partial `{ cards: {} }` is not a
 * lighter fixture, it is an impossible payload — and an actively harmful one:
 * `visibleOrderedSections` keeps every section the preferences do not hide, so
 * each renderer receives `undefined`, `BriefingCard` reads `.status` off it,
 * and the error boundary replaces the WHOLE dashboard with "Error in
 * dashboard". Landmark assertions still pass on that fallback, and an axe scan
 * still reports zero violations — on a page that is not the dashboard.
 *
 * Found 2026-08-03: three specs shared that payload, including the one whose
 * title claims the authenticated dashboard scans clean.
 *
 * `empty` rather than `not_configured`: a not-configured card renders nothing,
 * which would leave the grid — and anything a scan or a test looks for inside
 * it — absent for a different reason.
 */
export const briefingCardsMock: MockRoute = {
  url: '**/api/v1/briefing/cards',
  json: {
    cards: Object.fromEntries(
      [
        'weather',
        'agenda',
        'mails',
        'birthdays',
        'health',
        'tasks',
        'documents',
        'reminders',
        'for_you',
      ].map(name => [
        name,
        {
          status: 'empty',
          data: null,
          generated_at: '2026-08-03T08:00:00Z',
          error_code: null,
          error_message: null,
        },
      ])
    ),
  },
};
