/** Both knowledge-space doors use literal metadata criteria at a narrow viewport. */
import AxeBuilder from '@axe-core/playwright';
import { test, expect, openListFilters } from '../fixtures';
import type { RAGSpace } from '../../src/types/rag-spaces';

for (const width of [390, 1280]) {
  test(`space favorites persist and managed filtering composes at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await authenticate({ language: 'fr' });
    let favorite = false;
    let reject = false;
    const managed: RAGSpace = {
      id: '11111111-1111-4111-8111-111111111111',
      name: 'Réponses conservées',
      description: null,
      is_active: false,
      is_favorite: false,
      kind: 'bookmarks',
      document_count: 2,
      ready_document_count: 2,
      total_size: 20,
      created_at: '2026-11-01T12:00:00Z',
      updated_at: '2026-11-01T12:00:00Z',
    };
    const personal: RAGSpace = {
      ...managed,
      id: '22222222-2222-4222-8222-222222222222',
      name: 'Recherche',
      kind: null,
    };
    await mockApi([
      {
        url: '**/api/v1/rag-spaces*',
        handler: async route => {
          const query = new URL(route.request().url()).searchParams.get('q') ?? '';
          const spaces = [{ ...managed, is_favorite: favorite }, personal].filter(space =>
            space.name.toLowerCase().includes(query.toLowerCase())
          );
          await route.fulfill({ json: { spaces, total: spaces.length } });
        },
      },
      {
        url: `**/api/v1/rag-spaces/${managed.id}`,
        method: 'PATCH',
        handler: async route => {
          if (reject) {
            await route.fulfill({ status: 503, json: { detail: 'Synthetic refusal' } });
            return;
          }
          const payload: unknown = route.request().postDataJSON();
          expect(payload).toEqual({ is_favorite: !favorite });
          favorite = !favorite;
          await route.fulfill({ json: { ...managed, is_favorite: favorite } });
        },
      },
    ]);
    await page.goto('/fr/dashboard/spaces');
    const toggle = page.getByRole('button', {
      name: 'Ajouter Réponses conservées aux favoris',
      exact: true,
    });
    await toggle.focus();
    await page.keyboard.press('Space');
    const favorites = page.getByRole('region', { name: 'Favoris', exact: true });
    await expect(favorites.getByText(managed.name, { exact: true })).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Retirer Réponses conservées des favoris' })
    ).toBeFocused();
    await page.reload();
    await expect(favorites).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath(`spaces-${width}.png`), fullPage: true });
    await openListFilters(page, 'Filtres');
    await page.getByRole('button', { name: 'Géré par LIA', exact: true }).click();
    await expect(page.getByText('Recherche', { exact: true })).toHaveCount(0);
    await page.getByRole('searchbox').fill('absent');
    await expect(page.getByText('Aucun espace correspondant', { exact: true })).toBeVisible();
    await page.getByRole('searchbox').fill('Réponses');
    await expect(favorites).toBeVisible();
    reject = true;
    await page.getByRole('button', { name: 'Retirer Réponses conservées des favoris' }).click();
    await expect(page.getByText('Impossible de modifier les favoris. Réessayez.')).toBeVisible();
    await expect(favorites).toBeVisible();
    reject = false;
    await page.getByRole('button', { name: 'Retirer Réponses conservées des favoris' }).click();
    await expect(
      page
        .getByRole('region', { name: 'Autres espaces', exact: true })
        .getByText(managed.name, { exact: true })
    ).toBeVisible();
    await expect(page.getByRole('searchbox')).toHaveValue('Réponses');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true
    );
  });
}

for (const path of ['/en/dashboard/spaces', '/en/dashboard/settings?section=rag-spaces']) {
  test(`space filtering and ordering at ${path}`, async ({ page, authenticate, mockApi }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await authenticate();
    const requests: URLSearchParams[] = [];
    const space = {
      id: '11111111-1111-4111-8111-111111111111',
      name: 'École',
      description: null,
      is_active: false,
      kind: null,
      document_count: 2,
      ready_document_count: 1,
      total_size: 20,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };
    await mockApi([
      {
        url: '**/api/v1/rag-spaces*',
        handler: async route => {
          const params = new URL(route.request().url()).searchParams;
          requests.push(params);
          const spaces = params.get('q') === 'absent' ? [] : [space];
          await route.fulfill({ json: { spaces, total: spaces.length } });
        },
      },
    ]);
    await page.goto(path);
    await expect(page.getByText('École', { exact: true })).toBeVisible();
    await openListFilters(page, 'Filters');
    await page.getByRole('combobox', { name: 'Search in', exact: true }).selectOption('filename');
    await page.getByRole('searchbox', { name: 'Search by filename' }).fill('été');
    await expect.poll(() => requests.at(-1)?.get('q')).toBe('été');
    expect(requests.at(-1)?.get('field')).toBe('filename');
    await page.getByRole('combobox', { name: 'Sort by', exact: true }).selectOption('files');
    await expect.poll(() => requests.at(-1)?.get('sort')).toBe('files');
    await page.getByRole('searchbox').fill('absent');
    await expect(page.getByText('No matching spaces', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Clear search', exact: true }).click();
    await expect(page.getByText('École', { exact: true })).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
    ).toBe(true);
    const toolbar = page.getByRole('searchbox').locator('xpath=../../..');
    await toolbar.evaluate(node => node.setAttribute('data-list-a11y', ''));
    expect(
      (await new AxeBuilder({ page }).include('[data-list-a11y]').analyze()).violations
    ).toEqual([]);
  });
}
