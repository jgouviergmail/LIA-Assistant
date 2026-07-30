/**
 * Personal CRM (N-09 + favorites) — the Relations page end to end.
 *
 * Unit tests cover the aggregation service and the presentational components.
 * The browser proves the doors and the journey: Relations holds a first-class
 * NAV slot since 2026-07-30 (it took the `spaces` slot — the chat indicator
 * keeps spaces one click away), the overview renders, the star moves a card
 * into the Favorites band, a card opens the 360° detail (client-state, no
 * route change), and "prepare a 360° point" deep-links the chat with a
 * `?intent=` (ADR-173).
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
      is_favorite: false,
      is_peer: false,
    },
    {
      display_name: 'Marie Leroy',
      identity_confidence: 'normalized',
      open_loops_count: 1,
      calls_count: 0,
      last_interaction_at: '2026-07-20T09:00:00Z',
      is_favorite: false,
      is_peer: false,
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
  is_favorite: false,
  is_peer: false,
};

const ROUTES: MockRoute[] = [
  { url: '**/api/v1/relations', method: 'GET', json: OVERVIEW },
  { url: '**/api/v1/relations/favorites/*', method: 'PUT', status: 204 },
  { url: '**/api/v1/relations/*', method: 'GET', json: DETAIL },
];

test.describe('relations CRM (N-09)', () => {
  test('is reached from the navigation bar', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard');

    // Relations holds a first-class nav slot since 2026-07-30 (default-locale
    // hrefs carry no /fr prefix — assert the journey, not the string).
    const navLink = page.getByRole('navigation').getByRole('link', { name: 'Relations' });
    await expect(navLink).toBeVisible();
    await navLink.click();
    await page.waitForURL(/\/dashboard\/relations/, { timeout: 30_000 });
    await expect(page.getByRole('heading', { level: 1, name: 'Relations' })).toBeVisible();
  });

  test('the star moves a card into the Favorites band without opening it', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/relations');
    await expect(page.getByText(NAME)).toBeVisible({ timeout: 30_000 });

    // No favorites yet: a single band.
    await expect(page.getByRole('heading', { name: /Favoris/ })).toHaveCount(0);
    await page.getByRole('button', { name: `Ajouter ${NAME} aux favoris` }).click();
    // Optimistic: the Favorites band appears with the starred card inside.
    const favoritesBand = page.locator('section', {
      has: page.getByRole('heading', { name: /Favoris/ }),
    });
    await expect(favoritesBand.getByText(NAME)).toBeVisible();
    // The 360° detail did NOT open (starring is not opening).
    await expect(page.getByText('Rendre la perceuse')).toHaveCount(0);
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
    // Anchored: the sibling star button is named "Ajouter <name> aux favoris"
    // and must not match (two buttons carry the name since favorites).
    await page.getByRole('button', { name: new RegExp(`^${NAME}`) }).click();
    await expect(page.getByText('Rendre la perceuse')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText('Anniversaire surprise')).toBeVisible();
    await expect(page.getByText('Aime la randonnée en montagne.')).toBeVisible();

    // Prepare 360° → chat intent (ADR-173).
    await page.getByRole('button', { name: /360/ }).click();
    await page.waitForURL(/\/dashboard\/chat\?intent=/, { timeout: 30_000 });
  });
});
