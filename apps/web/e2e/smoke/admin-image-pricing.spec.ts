/**
 * Admin screen smoke — image pricing table accessible names (audit F012).
 *
 * Hermetic: /auth/me returns a superuser, the pricing list is mocked, every
 * other API call dies on the 501 catch-all (sections other than the one under
 * test degrade behind their error boundaries — that is their contract).
 * Asserts, in a real browser with the real EN locale, that the actions cell
 * carries its column name and the row buttons expose translated names.
 */
import { test, expect, type MockRoute } from '../fixtures';

const pricingEntry = {
  id: '9a7c2c46-0000-4000-8000-000000000042',
  provider: 'openai',
  model: 'gpt-image-1',
  quality: 'high',
  size: '1024x1024',
  cost_per_image_usd: '0.1670',
  effective_from: '2026-01-01T00:00:00Z',
  is_active: true,
};

const adminData: MockRoute[] = [
  {
    url: '**/api/v1/admin/image-pricing/pricing*',
    json: { total: 1, page: 1, page_size: 20, total_pages: 1, entries: [pricingEntry] },
  },
];

test.describe('admin image pricing (superuser)', () => {
  test('actions cell and row buttons expose translated accessible names', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ is_superuser: true });
    await mockApi(adminData);

    // Master-detail shell: the deep link opens the pricing pane directly —
    // the admin sections are indexed deep-link targets since ADR-227.
    await page.goto('/en/dashboard/settings?section=admin-image-pricing');

    // The row renders from the mocked entry…
    await expect(page.getByRole('cell', { name: 'gpt-image-1' })).toBeVisible();
    // …its actions cell is named after the visible column header (F012)…
    const actionsCell = page.getByRole('cell', { name: 'Actions' }).last();
    await expect(actionsCell).toBeVisible();
    // …and the buttons inside carry their own translated names.
    await expect(actionsCell.getByRole('button', { name: 'Edit' })).toBeVisible();
  });
});
