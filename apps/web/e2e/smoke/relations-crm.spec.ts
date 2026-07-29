/**
 * Personal CRM (N-09) — the Relations page is reachable and works end to end.
 *
 * Unit tests cover the aggregation service and the two presentational
 * components. Only a browser proves the chain that made this feature INVISIBLE
 * before the fix: the page has no nav slot, so it is reached through the Quick
 * Access bar; the overview must render, a card must open the 360° detail
 * (client-state, no route change), and "prepare a 360° point" must deep-link
 * the chat with a `?intent=` (ADR-173).
 */
import { test, expect, type MockRoute } from '../fixtures';

const NAME = 'Gérard Dupont';

const OVERVIEW = {
  relations: [
    {
      display_name: NAME,
      identity_confidence: 'exact',
      open_loops_count: 2,
      calls_count: 1,
      last_interaction_at: '2026-07-28T09:00:00Z',
    },
    {
      display_name: 'Marie Leroy',
      identity_confidence: 'normalized',
      open_loops_count: 1,
      calls_count: 0,
      last_interaction_at: '2026-07-20T09:00:00Z',
    },
  ],
};

const DETAIL = {
  display_name: NAME,
  identity_confidence: 'exact',
  open_loops: [
    {
      id: 'l1',
      subject: 'Rendre la perceuse',
      direction: 'user_owes',
      due_hint: null,
      days_open: 4,
    },
  ],
  recent_calls: [
    {
      id: 'c1',
      objective: 'Anniversaire surprise',
      outcome: 'objective_met',
      summary: 'Il est partant.',
      created_at: '2026-07-25T10:00:00Z',
    },
  ],
  memories: [{ id: 'm1', content: 'Aime la randonnée en montagne.' }],
};

const ROUTES: MockRoute[] = [
  { url: '**/api/v1/relations', method: 'GET', json: OVERVIEW },
  { url: '**/api/v1/relations/*', method: 'GET', json: DETAIL },
];

test.describe('relations CRM (N-09)', () => {
  test('is reached from Quick Access on the dashboard', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard');

    // The CRM has no nav slot (R01 header clips at 5); Quick Access is its
    // only always-visible door — the exact gap the review caught.
    const link = page.getByRole('link', { name: /Relations/i });
    await expect(link.first()).toHaveAttribute('href', '/fr/dashboard/relations');
  });

  test('lists relationships and opens a 360° view that deep-links the chat', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/relations');

    // Overview: both people appear.
    await expect(page.getByText(NAME)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText('Marie Leroy')).toBeVisible();

    // Open the 360° detail (client state — the URL stays on /relations).
    await page.getByRole('button', { name: new RegExp(NAME) }).click();
    await expect(page.getByText('Rendre la perceuse')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText('Anniversaire surprise')).toBeVisible();
    await expect(page.getByText('Aime la randonnée en montagne.')).toBeVisible();

    // Prepare 360° → chat intent (ADR-173).
    await page.getByRole('button', { name: /360/ }).click();
    await page.waitForURL(/\/dashboard\/chat\?intent=/, { timeout: 30_000 });
  });
});
