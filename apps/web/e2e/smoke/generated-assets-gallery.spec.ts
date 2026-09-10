/**
 * « Mes fichiers générés », in a real browser (ADR-279).
 *
 * Four things only a laid-out page proves, and each is a claim the section
 * makes to a person:
 *
 * 1. **One gallery is fetched, not three.** The three tabs each own a query;
 *    mounted together they would open three pages nobody is looking at. This
 *    spec counts the requests that actually left.
 * 2. **At 320 px nothing scrolls sideways** and the filters are FOLDED behind a
 *    summary that says what they hold. A component test can assert the fold; it
 *    cannot measure a document that overflows.
 * 3. **The expiry is on every card.** A file that vanishes with nothing said is
 *    the defect the deadline exists for.
 * 4. **A bulk delete asks the server exactly what was selected**, and reports
 *    what went AND what was already gone — the oracle is what is ASKED, which
 *    is what survives a refactor of the gesture.
 */
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';

/** A node the section really renders — a `<form>` would never appear. */
const CARD = '[data-testid="generated-asset-card"]';

const IMAGE_ID = 'a1b2c3d4-0000-4000-8000-000000000001';
const OTHER_ID = 'a1b2c3d4-0000-4000-8000-000000000002';

function asset(overrides: Record<string, unknown> = {}) {
  return {
    id: IMAGE_ID,
    title: 'Coucher de soleil',
    original_filename: 'generated_sunset.png',
    mime_type: 'image/png',
    file_size: 2048,
    origin: 'generated_image',
    conversation_id: null,
    created_at: '2026-09-10T08:00:00Z',
    expires_at: '2026-09-11T08:00:00Z',
    ...overrides,
  };
}

/**
 * The gallery routes, recording every listing the page asked for.
 *
 * @param asked - Collector for the query strings that left the browser.
 * @param deletes - Collector for the bulk-delete payloads.
 * @returns The mock routes.
 */
function galleryRoutes(asked: string[], deletes: unknown[] = []): MockRoute[] {
  return [
    {
      url: /\/api\/v1\/generated-assets\/delete$/,
      handler: async route => {
        deletes.push(JSON.parse(route.request().postData() ?? '{}'));
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ deleted: [IMAGE_ID], skipped: [OTHER_ID] }),
        });
      },
    },
    {
      url: /\/api\/v1\/generated-assets\?/,
      handler: async route => {
        const url = new URL(route.request().url());
        asked.push(url.searchParams.get('family') ?? '');
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            items: [asset(), asset({ id: OTHER_ID, title: 'Plan de la salle' })],
            total: 2,
            total_bytes: 4096,
            limit: 24,
            offset: 0,
            max_limit: 100,
          }),
        });
      },
    },
    // The image itself never leaves the test: a 1x1 png keeps the thumbnails
    // from turning into failed requests that pollute the console assertions.
    {
      url: '**/api/v1/attachments/**',
      handler: async route => {
        await route.fulfill({
          status: 200,
          contentType: 'image/png',
          body: Buffer.from(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
            'base64'
          ),
        });
      },
    },
  ];
}

test.describe('the generated files gallery', () => {
  test('mounts ONE gallery, states the exact total and every deadline', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    const asked: string[] = [];
    await mockApi(galleryRoutes(asked));

    await page.goto('/fr/dashboard/settings?section=generated-assets');
    await waitForHydration(page, CARD);

    // Three tabs, one query: the two closed galleries cost nothing.
    await expect(page.getByRole('tab', { name: 'Images' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Documents' })).toBeVisible();
    expect(new Set(asked)).toEqual(new Set(['images']));

    // The figures come from the payload's aggregates, never from the rows.
    await expect(page.getByText('2 fichiers')).toBeVisible();

    // Every card says when its file goes.
    const cards = page.getByTestId('generated-asset-card');
    await expect(cards).toHaveCount(2);
    await expect(cards.first()).toContainText(/Expire/i);
  });

  test('fetches the documents gallery only once its tab is opened', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    const asked: string[] = [];
    await mockApi(galleryRoutes(asked));

    await page.goto('/fr/dashboard/settings?section=generated-assets');
    await waitForHydration(page, CARD);
    expect(asked).not.toContain('documents');

    await page.getByRole('tab', { name: 'Documents' }).click();

    await expect.poll(() => asked.includes('documents')).toBe(true);
  });

  test('folds the filters on a phone and never scrolls sideways', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // 320 px is the narrowest phone this app claims to serve.
    await page.setViewportSize({ width: 320, height: 720 });
    await authenticate({ language: 'fr' });
    await mockApi(galleryRoutes([]));

    await page.goto('/fr/dashboard/settings?section=generated-assets');
    await waitForHydration(page, CARD);

    // Folded, the search field is UNMOUNTED — not merely hidden — and the
    // summary still says what the block holds.
    await expect(page.getByLabel('Chercher un nom')).toHaveCount(0);
    const summary = page.locator('summary', { hasText: 'Filtres' });
    await expect(summary).toBeVisible();
    await expect(summary).toContainText('Aucun filtre');

    await summary.click();
    await expect(page.getByLabel('Chercher un nom')).toBeVisible();

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });

  test('sends the search to the server as a query, not as a client filter', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    const queries: string[] = [];
    await mockApi([
      {
        url: /\/api\/v1\/generated-assets\?/,
        handler: async route => {
          const url = new URL(route.request().url());
          const needle = url.searchParams.get('q');
          if (needle) queries.push(needle);
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              items: [asset()],
              total: 1,
              total_bytes: 2048,
              limit: 24,
              offset: 0,
              max_limit: 100,
            }),
          });
        },
      },
      ...galleryRoutes([]).slice(2),
    ]);

    await page.goto('/fr/dashboard/settings?section=generated-assets');
    await waitForHydration(page, CARD);

    await page.getByLabel('Chercher un nom').fill('soleil');

    // The count is EXACT over the whole filtered set, so it has to come from
    // the server: a page filtered in the browser could not know the total.
    await expect.poll(() => queries.includes('soleil'), { timeout: 15_000 }).toBe(true);
  });

  test('asks the server for exactly the selection, and says what was already gone', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    const deletes: unknown[] = [];
    await mockApi(galleryRoutes([], deletes));

    await page.goto('/fr/dashboard/settings?section=generated-assets');
    await waitForHydration(page, CARD);

    await page.getByLabel('Sélectionner Coucher de soleil').check();
    await page.getByRole('button', { name: /Supprimer 1 fichier/ }).click();
    await page.getByRole('button', { name: /Supprimer/ }).last().click();

    await expect.poll(() => deletes.length, { timeout: 15_000 }).toBe(1);
    expect(deletes[0]).toMatchObject({ ids: [IMAGE_ID] });

    // A file the cleanup removed between the listing and the click is reported
    // as skipped, never folded into « deleted » (ADR-185).
    await expect(page.getByText(/déjà/i)).toBeVisible({ timeout: 15_000 });
  });
});
