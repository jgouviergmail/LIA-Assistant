/**
 * The connector-health banner is visible, and it does not cost the composer.
 *
 * Two properties that only a browser can prove:
 *
 * 1. **It is there.** Until 2026-07-30 the only surface saying a connector was
 *    broken was a modal shown once and then suppressed for hours. Five
 *    connectors sat in ERROR for a full day while their owner believed
 *    everything worked — and a peer's assistant kept reading his shared
 *    calendar and getting nothing.
 * 2. **It does not push the composer below the fold.** The chat shell is sized
 *    `100dvh` minus a CONSTANT for the chrome above it. That constant predates
 *    the banner, so inserting a block in that flow silently broke the one
 *    invariant `chat-composer-in-viewport.spec.ts` exists to protect. The fix
 *    (the banner publishes its measured height as `--connector-banner-h`,
 *    default `0px`) is only real if a browser lays it out — jsdom has no
 *    layout, and the unit tests cannot see this class of defect at all.
 */
import { test, expect, type MockRoute } from '../fixtures';

const BROKEN_CONNECTOR = {
  id: 'conn-google-calendar',
  connector_type: 'google_calendar',
  display_name: 'Google Calendar',
  health_status: 'error',
  severity: 'critical',
  expires_in_minutes: null,
  authorize_url: '/connectors/google_calendar/authorize',
};

/** Overrides the shell's healthy default (routes are LIFO — last wins). */
const BROKEN_HEALTH: MockRoute[] = [
  {
    url: '**/api/v1/connectors/health',
    json: {
      connectors: [BROKEN_CONNECTOR],
      has_issues: true,
      critical_count: 1,
      warning_count: 0,
      checked_at: '2026-07-30T10:00:00Z',
    },
  },
  {
    url: '**/api/v1/conversations/me/messages*',
    json: {
      messages: [],
      conversation_id: null,
      total_count: 0,
      has_more: false,
      next_cursor: null,
    },
  },
  { url: '**/api/v1/conversations/me/totals', json: {} },
  { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
  { url: '**/api/v1/agents/runs/active', json: { active: false } },
  { url: '**/api/v1/agents/hitl/pending', json: null },
  { url: '**/api/v1/usage/**', json: {} },
];

test.describe('connector health banner', () => {
  test('names the broken connector and offers the fix', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(BROKEN_HEALTH);
    await page.goto('/fr/dashboard');

    const banner = page.getByRole('status', { name: /connexions/i });
    await expect(banner).toBeVisible();
    await expect(banner).toContainText('Google Calendar');
    await expect(banner.getByRole('button', { name: /reconnecter/i })).toBeVisible();
  });

  test('the composer stays in the viewport while the banner is shown', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(BROKEN_HEALTH);
    await page.setViewportSize({ width: 390, height: 800 });
    await page.goto('/fr/dashboard/chat');

    const composer = page.locator('textarea').first();
    await composer.waitFor({ state: 'visible' });
    await expect(page.getByRole('status', { name: /connexions/i })).toBeVisible();

    // Polled: the banner mounts after the first paint (health poll) and the
    // shell re-computes when `--connector-banner-h` lands, so a single read can
    // catch the layout mid-flight.
    await expect
      .poll(
        async () => {
          const box = await composer.boundingBox();
          return box ? Math.round(box.y + box.height) : Number.NaN;
        },
        { message: 'the banner pushed the composer below the fold' }
      )
      .toBeLessThanOrEqual(800);

    // …and it must not have been made to fit by growing a page scrollbar.
    await expect
      .poll(
        async () =>
          page.evaluate(() => {
            const el = document.scrollingElement ?? document.documentElement;
            return el.scrollHeight - el.clientHeight;
          }),
        { message: 'the page scrolls, so the shell exceeds the viewport' }
      )
      .toBeLessThanOrEqual(1);
  });

  test('the banner publishes a non-zero height and no horizontal overflow', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(BROKEN_HEALTH);
    await page.setViewportSize({ width: 390, height: 800 });
    await page.goto('/fr/dashboard/chat');
    await expect(page.getByRole('status', { name: /connexions/i })).toBeVisible();

    // The variable is the whole contract with the chat shell: `0px` here would
    // mean the shell subtracted nothing and the previous assertion passed by
    // luck.
    await expect
      .poll(
        async () =>
          page.evaluate(() =>
            parseFloat(
              getComputedStyle(document.documentElement).getPropertyValue(
                '--connector-banner-h'
              ) || '0'
            )
          ),
        { message: '--connector-banner-h must carry the measured height' }
      )
      .toBeGreaterThan(0);

    const overflow = await page.evaluate(() => {
      const el = document.scrollingElement ?? document.documentElement;
      return el.scrollWidth - el.clientWidth;
    });
    expect(overflow, 'the banner must not widen the page at 390 px').toBeLessThanOrEqual(1);
  });
});
