/** Literal criteria, stable paging, honest failures and a narrow native toolbar. */
import AxeBuilder from '@axe-core/playwright';
import { test, expect } from '../fixtures';

test('activity filters, account dates and pagination stay coherent', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Pacific/Auckland' });
  const requests: URLSearchParams[] = [];
  const cut = '2026-11-01T12:00:00Z';
  let fail = false;
  await mockApi([
    { url: '**/api/v1/config', json: { features: { activity_timeline_enabled: true } } },
    {
      url: '**/api/v1/activity/timeline*',
      handler: async route => {
        const params = new URL(route.request().url()).searchParams;
        requests.push(params);
        if (fail) {
          await route.fulfill({ status: 503, json: { detail: 'temporarily_unavailable' } });
          return;
        }
        const offset = Number(params.get('offset') ?? 0);
        const empty = params.get('q') === 'absent';
        await route.fulfill({
          json: {
            events: empty
              ? []
              : [
                  {
                    kind: 'journal_entry',
                    ref_id: String(offset),
                    text: offset ? 'Older note' : 'Été note',
                    occurred_at: '2026-10-31T11:30:00Z',
                    status: null,
                  },
                ],
            totals: [{ kind: 'journal_entry', total: empty ? 0 : 26, truncated: false }],
            offset,
            limit: 25,
            has_more: !empty && offset === 0,
            failed_kinds: [],
            window_days: 30,
            criteria: {
              q: params.get('q') ?? '',
              kinds: params.getAll('kinds'),
              sort: params.get('sort') ?? 'recent',
              as_of: params.get('as_of') ?? cut,
            },
          },
        });
      },
    },
  ]);
  await page.goto('/en/dashboard/activity');
  await expect(page.getByText('Été note', { exact: true })).toBeVisible();
  await expect(page.locator('time')).toHaveText('12:30 AM');
  await page.getByRole('button', { name: 'Show more', exact: true }).click();
  await expect(page.getByText('Older note', { exact: true })).toBeVisible();
  expect(requests.at(-1)?.get('as_of')).toBe(cut);
  await page.getByRole('searchbox').fill('été');
  await expect.poll(() => requests.at(-1)?.get('q')).toBe('été');
  expect(requests.at(-1)?.get('offset')).toBe('0');
  await expect(page.getByText('Older note', { exact: true })).toHaveCount(0);
  await page.getByRole('combobox', { name: 'Category', exact: true }).selectOption('journal_entry');
  await page.getByRole('combobox', { name: 'Sort by', exact: true }).selectOption('oldest');
  await expect.poll(() => requests.at(-1)?.get('sort')).toBe('oldest');
  expect(requests.at(-1)?.getAll('kinds')).toEqual(['journal_entry']);
  fail = true;
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(
    page.getByText('Refresh failed. The previous results remain displayed.')
  ).toBeVisible();
  await expect(page.getByText('Été note', { exact: true })).toBeVisible();
  fail = false;
  await page.getByRole('searchbox').fill('absent');
  await expect(page.getByText('No matching activity', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Clear filters', exact: true }).click();
  await expect(page.getByText('Été note', { exact: true })).toBeVisible();
  const toolbar = page.getByRole('searchbox').locator('xpath=../../..');
  await toolbar.evaluate(node => node.setAttribute('data-list-a11y', ''));
  expect((await new AxeBuilder({ page }).include('[data-list-a11y]').analyze()).violations).toEqual(
    []
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
