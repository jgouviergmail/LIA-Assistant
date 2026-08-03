/**
 * Settings deep links (W2) — `?section=` actually opens the section.
 *
 * The settings page stacks ~30 collapsed accordion sections over two tabs.
 * `?section=` used to understand exactly two tokens, while the getting-started
 * checklist pointed SIX of its seven items at the bare page: "choose a
 * personality" landed the user at the top of a wall of closed accordions.
 *
 * Unit tests keep the table aligned with the components that declare each
 * accordion value. Only a browser can prove the rest of the chain: the tab is
 * activated, the item is EXPANDED, and the URL is cleaned so a reload does not
 * replay the navigation.
 */
import { test, expect, type MockRoute } from '../fixtures';

/**
 * Deliberately MINIMAL.
 *
 * Mocking each settings subsystem turned out to make the run erratic: a broad
 * pattern such as `**​/api/v1/connectors/**` shadows narrower shell mocks
 * (Playwright routes are LIFO), and the sections then render — or not —
 * depending on which one won. The routing mechanism under test does not need
 * any of that data: unmocked endpoints hit the 501 catch-all, which every
 * section is built to survive (that is what `FeatureErrorBoundary` is for).
 */
const ROUTES: MockRoute[] = [
  { url: '**/api/v1/connectors', json: { connectors: [] } },
  { url: '**/api/v1/scheduled-actions**', json: { actions: [], total: 0 } },
  { url: '**/api/v1/usage/**', json: {} },
  // `OpenLoopsSection` self-gates on this flag and renders NOTHING without it,
  // so the commitments case below needs the instance to declare the capability.
  // Narrow and additive: every other section reads flags that stay absent here,
  // and an absent flag is falsy exactly as it was when nothing answered.
  {
    url: '**/api/v1/config',
    json: {
      sse: { heartbeat_interval_seconds: 30 },
      rate_limits: { enabled: false, per_minute: 60, burst: 10 },
      i18n: { supported_languages: ['fr', 'en'], default_language: 'en' },
      features: { open_loops_enabled: true },
      api_version: 'v1',
    },
  },
  { url: '**/api/v1/open-loops**', json: { items: [], total: 0 } },
];

/**
 * Tokens exercised here, paired with the accordion value the page must expand.
 *
 * Kept explicit rather than imported from the app: an e2e that reads the very
 * table it verifies would still pass if that table drifted.
 *
 * Coverage is deliberately partial. Several sections are gate-kept (ADR-061) or
 * return null until their own data resolves — `HeartbeatSettings` and
 * `SkillsSettings` among them — so reproducing them here would mean mocking
 * each subsystem's full payload just to assert a routing mechanism that is
 * identical for all of them. The sample below spans BOTH tabs and both
 * accordion states (superuser and not), which is what the mechanism actually
 * depends on; the completeness of the table itself — every token resolving to
 * an accordion value a component really declares — is asserted in
 * `lib/__tests__/settings-sections.test.ts`.
 */
const CASES = [
  // Preferences tab
  { token: 'connectors', value: 'connectors' },
  { token: 'voice-mode', value: 'voice-mode' },
  // Features tab — reached only after the tab switch, which is the part of the
  // mechanism worth proving in a browser (Radix mounts tab content lazily).
  { token: 'personality', value: 'personality' },
  { token: 'memories', value: 'memories' },
  { token: 'interests', value: 'interests' },
  { token: 'scheduled-actions', value: 'scheduled-actions' },
  { token: 'journals', value: 'journals' },
  // The destination of the dashboard's "For you" commitments card. That card
  // linked to the bare settings page until 2026-08-03, so someone following
  // "you have 3 open commitments" landed on a wall of closed accordions with
  // no commitments in sight — the exact failure this file was written for,
  // reappearing at a new call site. Pinned here so the link keeps arriving.
  { token: 'open-loops', value: 'open-loops' },
] as const;

test.describe('settings deep links', () => {
  for (const { token, value } of CASES) {
    test(`?section=${token} expands its section`, async ({ page, authenticate, mockApi }) => {
      await authenticate({ language: 'fr' });
      await mockApi(ROUTES);
      await page.goto(`/fr/dashboard/settings?section=${token}`);

      // Radix marks the open item with data-state="open" on the AccordionItem,
      // which carries the id derived from the same accordion value.
      //
      // The generous timeout is the cost of the dev server, not a product
      // signal: the settings page mounts ~30 sections, each with its own
      // queries, and under a full sequential suite the on-demand compilation
      // makes first paint slow. Against the CI production build this resolves
      // immediately. Waiting explicitly beats an intermittent red.
      const item = page.locator(`#settings-section-${value}`);
      await expect(item, `${token} must resolve to a section`).toBeAttached({ timeout: 20_000 });
      await expect(item, `${token} must be expanded`).toHaveAttribute('data-state', 'open', {
        timeout: 10_000,
      });
    });
  }

  test('cleans the parameter so a reload does not replay the jump', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/settings?section=personality');
    await expect(page.locator('#settings-section-personality')).toHaveAttribute(
      'data-state',
      'open',
      { timeout: 10_000 }
    );
    expect(new URL(page.url()).searchParams.get('section')).toBeNull();
  });

  test('an unknown token leaves the page on its default tab', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // A stale bookmark must not throw, and must not open something arbitrary.
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/settings?section=does-not-exist');

    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    const open = page.locator('[id^="settings-section-"][data-state="open"]');
    await expect(open).toHaveCount(0);
    expect(new URL(page.url()).searchParams.get('section')).toBeNull();
  });
});
