/**
 * The administrators' user table keeps who each row is on screen.
 *
 * Hermetic: the listing is mocked. Four claims only a laid-out page proves:
 *
 * 1. **Scrolled to its last column, the email and the name have not moved**
 *    (from the product's 880 px boundary up) — every switch now closes the
 *    table, forty-five columns wide, and a row that loses its name is a row
 *    nobody can act on.
 * 2. **On a phone only the email stays**: two frozen columns would leave almost
 *    nothing to scroll.
 * 3. **The page itself never scrolls sideways** — the table does. The cells'
 *    `sr-only` state labels are absolutely positioned: without a positioned
 *    scroller they escaped its clipping and widened the document by 2 407 px
 *    (measured at 390 px before the fix).
 * 4. **The header sorts from the keyboard.**
 */
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const SWITCHES = [
  'memory_enabled',
  'psyche_enabled',
  'psyche_display_avatar',
  'habits_enabled',
  'journals_enabled',
  'journal_consolidation_enabled',
  'journal_consolidation_with_history',
  'voice_enabled',
  'voice_mode_enabled',
  'phone_rich_context_enabled',
  'heartbeat_enabled',
  'interests_enabled',
  'relation_debrief_enabled',
  'image_generation_enabled',
  'image_generation_prompt_enhancement',
  'discovery_enabled',
  'peer_email_visible',
  'use_last_known_location',
  'login_notifications_enabled',
  'health_metrics_agents_enabled',
  'tokens_display_enabled',
  'debug_panel_enabled',
];

function row(index: number) {
  return {
    id: `00000000-0000-4000-8000-${String(index).padStart(12, '0')}`,
    email: `account.number.${index}@example.org`,
    full_name: `Account Holder ${index}`,
    is_active: true,
    is_verified: true,
    is_superuser: false,
    created_at: '2026-02-03T10:00:00Z',
    language: 'en',
    personality_id: null,
    ...Object.fromEntries(SWITCHES.map((key, i) => [key, (i + index) % 2 === 0])),
    last_login: null,
    last_message_at: '2026-09-20T08:00:00Z',
    total_messages: 120,
    total_tokens: 450000,
    tokens_in: 300000,
    tokens_out: 100000,
    tokens_cache: 50000,
    total_cost_eur: 12.5,
    total_google_api_requests: 40,
    cycle_messages: 12,
    cycle_tokens: 45000,
    cycle_google_api_requests: 4,
    cycle_cost_eur: 1.25,
    active_connectors_count: 3,
    memories_count: 12,
    interests_count: 2,
    skills_count: 1,
    mcp_servers_count: 0,
    scheduled_actions_count: 4,
    rag_spaces_count: 1,
    is_usage_blocked: false,
    deleted_at: null,
    is_deleted: false,
  };
}

function routes(asked: string[]): MockRoute[] {
  return [
    {
      url: /\/api\/v1\/users\/admin\/search\?/,
      handler: async route => {
        asked.push(new URL(route.request().url()).searchParams.get('sort_by') ?? '');
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            users: [row(1), row(2)],
            total: 2,
            page: 1,
            page_size: 20,
            total_pages: 1,
          }),
        });
      },
    },
  ];
}

/** The left edge of the first row's cell under the header named `name`. */
async function cellLeft(page: import('@playwright/test').Page, text: string): Promise<number> {
  const box = await page.getByRole('cell', { name: text, exact: true }).first().boundingBox();
  if (!box) throw new Error(`no cell ${text}`);
  return box.x;
}

async function scrollTableToTheEnd(page: import('@playwright/test').Page): Promise<void> {
  await page.locator('table').evaluate(table => {
    const scroller = table.parentElement;
    if (scroller) scroller.scrollLeft = scroller.scrollWidth;
  });
}

test.describe('the administrators’ user table', () => {
  test('keeps the email and the name in place while it scrolls', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'en', is_superuser: true });
    await mockApi(routes([]));
    await page.goto('/en/dashboard/settings?section=admin-users');
    await waitForHydration(page, 'table');

    const email = 'account.number.1@example.org';
    const name = 'Account Holder 1';
    const emailBefore = await cellLeft(page, email);
    const nameBefore = await cellLeft(page, name);
    await scrollTableToTheEnd(page);

    // The last switch is now in view, and the identity has not moved.
    await expect(page.getByRole('columnheader', { name: 'Debug panel' })).toBeInViewport();
    expect(Math.abs((await cellLeft(page, email)) - emailBefore)).toBeLessThan(1);
    expect(Math.abs((await cellLeft(page, name)) - nameBefore)).toBeLessThan(1);
  });

  test('on a phone only the email stays, and the page never scrolls sideways', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await authenticate({ language: 'en', is_superuser: true });
    await mockApi(routes([]));
    await page.goto('/en/dashboard/settings?section=admin-users');
    await waitForHydration(page, 'table');
    await awaitStyledPage(page, 'admin users at 390 px');

    const email = 'account.number.1@example.org';
    const name = 'Account Holder 1';
    const emailBefore = await cellLeft(page, email);
    const nameBefore = await cellLeft(page, name);
    await expectNoOverflow(page, 'before scrolling the table');
    await scrollTableToTheEnd(page);

    expect(Math.abs((await cellLeft(page, email)) - emailBefore)).toBeLessThan(1);
    expect(await cellLeft(page, name)).toBeLessThan(nameBefore - 100);
    await expectNoOverflow(page, 'scrolled to the last column');
  });

  test('sorts by a switch from the keyboard', async ({ page, authenticate, mockApi }) => {
    const asked: string[] = [];
    await authenticate({ language: 'en', is_superuser: true });
    await mockApi(routes(asked));
    await page.goto('/en/dashboard/settings?section=admin-users');
    await waitForHydration(page, 'table');

    // Scoped to the table: the settings menu has a section of that name too.
    await page.locator('table').getByRole('button', { name: 'Proactive notifications' }).focus();
    await page.keyboard.press('Enter');

    await expect.poll(() => asked.at(-1)).toBe('heartbeat_enabled');
    await expect(
      page.locator('table').getByRole('columnheader', { name: 'Proactive notifications' })
    ).toHaveAttribute('aria-sort', 'ascending');
  });
});
