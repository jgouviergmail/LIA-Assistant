/**
 * The habits panel — what LIA learned, told in the person's own words.
 *
 * ADR-214 ships the CONTROL before any consumption: everything the nightly
 * job learned is visible here, legible, and reversible. Three claims only a
 * browser can prove, each paid for once:
 *
 * - a recurring request names what is usually asked and its domains through
 *   the register's vocabulary (« Search · Emails + Contacts »), never as the
 *   raw `email+contact` signature the ledger stores — the unit tests see the
 *   i18n MOCK echo keys, so only a real render shows what a person reads;
 * - when the instance does not offer automations in the chat, the panel says
 *   so instead of letting the person wait for an offer that cannot come
 *   (ADR-184: an enforced setting is published);
 * - the pause is one click and one exact write (`POST /habits/{id}/status`),
 *   and the whole section fits a 320 px phone without a horizontal scroll.
 */
import { test, expect, type MockRoute } from '../fixtures';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const RECURRING_ID = '00000000-0000-4000-8000-0000000000a1';

/** Mirrors `AppConfig` (src/hooks/useAppConfig.ts) with the habits flag ON. */
const APP_CONFIG = {
  sse: { heartbeat_interval_seconds: 30 },
  rate_limits: { enabled: false, per_minute: 60, burst: 10 },
  i18n: { supported_languages: ['en', 'fr', 'de', 'es', 'it', 'zh'], default_language: 'en' },
  features: {
    tool_approval_enabled: false,
    attachments_enabled: true,
    rag_spaces_enabled: true,
    rag_spaces_embedding_model: 'text-embedding-3-small',
    journals_enabled: false,
    habits_enabled: true,
    heartbeat_enabled: true,
    workboard_enabled: true,
  },
  api_version: 'v1',
};

/** One 24-slot presence vector with a morning peak (heatmap source). */
const MORNING_BINS = Array.from({ length: 24 }, (_, hour) =>
  hour >= 8 && hour < 10 ? 0.9 : hour >= 6 && hour < 12 ? 0.3 : 0
);

/** Mirrors `HabitsOverview` (src/hooks/useHabits.ts). */
const OVERVIEW = {
  habits_enabled: true,
  profile: {
    computed_at: '2026-09-10T02:15:00Z',
    weekday: {
      verdict: 'windows',
      windows: [{ start_hour: 8, end_hour: 10, presence: 0.86 }],
      n_eff: 21.4,
      required_n_eff: 8,
      effective_presence_min: 0.55,
      bin_presence: MORNING_BINS,
    },
    weekend: {
      verdict: 'none',
      windows: [],
      n_eff: 6.2,
      required_n_eff: 4,
      effective_presence_min: 0.71,
      bin_presence: MORNING_BINS.map(v => v * 0.2),
    },
    active_days_fraction: 0.62,
    sparse: false,
  },
  streak: { current: 5, longest: 12, milestone_reached: null, next_milestone: 7 },
  habits: [
    {
      id: RECURRING_ID,
      kind: 'recurring_request',
      key: 'email+contact',
      // The ledger's dominant request (ADR-214 c): the row opens with it.
      payload: { shape: 'daily', trigger_hour: 8.5, days_of_week: [], usual_intent: 'search' },
      status: 'active',
      positive_signals: 4,
      negative_signals: 0,
      last_observed_at: '2026-09-10T06:40:00Z',
      created_at: '2026-09-01T02:15:00Z',
    },
  ],
  candidates: [{ key: 'email+task', observed_days: 2, required_days: 4, origin: 'live' }],
  candidates_more: 0,
  // The one instance flag the learning does NOT depend on.
  chat_suggestions_enabled: false,
};

const ROUTES: MockRoute[] = [
  { url: '**/api/v1/config', json: APP_CONFIG },
  { url: '**/api/v1/habits', method: 'GET', json: OVERVIEW },
];

test.describe('habits settings panel', () => {
  test('what was learned reads in the vocabulary of the person, with the instance limits stated', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'en' });
    await mockApi(ROUTES);
    await page.goto('/en/dashboard/settings?section=habits');

    await expect(page.getByRole('heading', { name: 'Habits' })).toBeVisible({ timeout: 20_000 });

    // The rhythm: a learned weekday window is a chip; a weekend without one
    // says so AND publishes the bar it failed (ADR-184), never a blank.
    await expect(page.getByText('08:00–10:00')).toBeVisible();
    await expect(page.getByText('no stable time habit detected')).toBeVisible();
    await expect(page.getByText(/present on ≥ 71% of days/)).toBeVisible();

    // A recurring request is named by its domains, through the register's
    // own vocabulary — the raw signature never reaches the screen.
    await expect(page.getByText(/Search · Emails \+ Contacts — every day ~08:30/)).toBeVisible();
    await expect(page.getByText('email+contact')).toHaveCount(0);
    await expect(page.getByText('5 days in a row')).toBeVisible();
    await expect(page.getByText('Active', { exact: true })).toBeVisible();

    // The candidate under observation states its quantified progress toward
    // the ENFORCED existence gate, and the vocabulary rule holds there too.
    await expect(page.getByRole('progressbar').first()).toBeVisible();
    await expect(page.getByText('2/4 distinct days')).toBeVisible();
    await expect(page.getByText(/Emails \+ Tasks/)).toBeVisible();

    // The chat will not offer an automation on this instance: said, once.
    await expect(
      page.getByText('On this instance LIA does not offer an automation in the chat', {
        exact: false,
      })
    ).toBeVisible();
  });

  test('pausing a habit is one click and one exact write', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const writes: Array<{ url: string; body: unknown }> = [];
    await authenticate({ language: 'en' });
    await mockApi([
      ...ROUTES,
      {
        url: `**/api/v1/habits/${RECURRING_ID}/status`,
        method: 'POST',
        handler: async route => {
          writes.push({ url: route.request().url(), body: route.request().postDataJSON() });
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ ...OVERVIEW.habits[0], status: 'paused' }),
          });
        },
      },
    ]);
    await page.goto('/en/dashboard/settings?section=habits');
    await expect(page.getByText(/Emails \+ Contacts/)).toBeVisible({ timeout: 20_000 });

    await page.getByRole('button', { name: 'Pause' }).click();

    await expect.poll(() => writes.length, { timeout: 10_000 }).toBe(1);
    expect(writes[0].url).toContain(`/api/v1/habits/${RECURRING_ID}/status`);
    expect(writes[0].body).toEqual({ status: 'paused' });
  });

  test('the whole panel fits a 320 px phone without a horizontal scroll', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'en' });
    await mockApi(ROUTES);
    await page.setViewportSize({ width: 320, height: 800 });
    await page.goto('/en/dashboard/settings?section=habits');
    await awaitStyledPage(page, '/dashboard/settings?section=habits @320px');

    await expect(page.getByText(/Emails \+ Contacts/)).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText('2/4 distinct days')).toBeVisible();

    await expectNoOverflow(page, 'habits section at 320px');
  });
});
