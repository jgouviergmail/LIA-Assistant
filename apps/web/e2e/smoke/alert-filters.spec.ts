/** Real hub controls with controlled HTTP: independent sections and bounded SMS refusals. */
import AxeBuilder from '@axe-core/playwright';
import { test, expect, idleNotificationStream, openListFilters } from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';
import type { SmsPage, SmsQuery, SmsDisplayOrder } from '../../src/types/sms';

test('alert filters preserve rubrics, lazy reads, proposals and SMS period recovery', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Pacific/Auckland', language: 'en' });
  const cut = '2026-11-01T12:00:00Z';
  const reads: URLSearchParams[] = [];
  const smsReads: (SmsQuery & SmsDisplayOrder)[] = [];
  let proposals = 0;
  let refusal: string | null = null;
  await mockApi([
    idleNotificationStream,
    { url: '**/api/v1/notifications/broadcasts/unread', json: { broadcasts: [] } },
    {
      url: '**/api/v1/config',
      json: {
        ...appConfig,
        features: {
          ...appConfig.features,
          sms_enabled: true,
          habits_enabled: true,
          workboard_enabled: false,
        },
      },
    },
    {
      url: '**/api/v1/notifications/hub-counts',
      json: { reminders: 21, scheduled: 0, interests: 0, offers: 0, sms: 2 },
    },
    {
      url: '**/api/v1/habits/proposals*',
      handler: async route => {
        proposals++;
        expect([...new URL(route.request().url()).searchParams.keys()].sort()).toEqual([
          'limit',
          'offset',
        ]);
        await route.fulfill({ json: { proposals: [], total: 0, learning_enabled: false } });
      },
    },
    {
      url: '**/api/v1/reminders*',
      handler: async route => {
        const params = new URL(route.request().url()).searchParams;
        reads.push(params);
        await route.fulfill({
          json: {
            reminders: [
              {
                id: 'reminder',
                content:
                  params.get('q') ||
                  (params.get('offset') === '0' ? 'First reminder' : 'Next reminder'),
                trigger_at: cut,
              },
            ],
            total: 21,
            as_of: cut,
          },
        });
      },
    },
    {
      url: '**/api/v1/sms/display-search',
      method: 'POST',
      handler: async route => {
        const query: SmsQuery & SmsDisplayOrder = route.request().postDataJSON();
        smsReads.push(query);
        if (refusal) {
          await route.fulfill({ status: 409, json: { detail: { error_code: refusal } } });
          return;
        }
        const payload: SmsPage = {
          items: [
            {
              id: '10000000-0000-4000-8000-000000000001',
              sender: 'Camille',
              display_name: 'Camille',
              body: '<script>literal message</script>',
              received_at: '2026-10-31T11:30:00Z',
              date_kind: 'received',
              origin: 'iphone',
              identity_source: 'raw',
              identity_state: 'unresolved',
              relation_key: null,
            },
          ],
          total: 1,
          as_of: cut,
          revision: 1,
          next_cursor: null,
        };
        await route.fulfill({ json: payload });
      },
    },
  ]);
  await page.goto('/en/dashboard/notifications');
  const reminders = page
    .locator('details')
    .filter({ has: page.locator('summary').getByText('Reminders', { exact: true }) });
  const offers = page
    .locator('details')
    .filter({ has: page.locator('summary').getByText('Proposals', { exact: true }) });
  await expect(reminders.locator('summary')).toBeVisible();
  // A phone: the category and the order wait behind « Filters », and the
  // rubrics still start under the opened block.
  await openListFilters(page, 'Filters');
  const filterBox = await page
    .getByRole('combobox', { name: 'Category', exact: true })
    .boundingBox();
  const offersBox = await offers.boundingBox();
  expect(filterBox).not.toBeNull();
  expect(offersBox).not.toBeNull();
  expect(offersBox!.y).toBeGreaterThanOrEqual(filterBox!.y + filterBox!.height);
  expect(reads).toHaveLength(0);
  await offers.locator('summary').click();
  await reminders.locator('summary').click();
  await expect(reminders.getByText('First reminder', { exact: true })).toBeVisible();
  await reminders.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(reminders.getByText('Next reminder', { exact: true })).toBeVisible();
  expect(reads.at(-1)?.get('as_of')).toBe(cut);
  await page.getByRole('searchbox', { name: 'Search alerts' }).fill('été');
  await expect(reminders.getByText('été', { exact: true })).toBeVisible();
  expect(reads.at(-1)?.get('offset')).toBe('0');
  await page.getByRole('combobox', { name: 'Sort by', exact: true }).selectOption('name');
  await expect.poll(() => reads.at(-1)?.get('sort')).toBe('name');
  expect(proposals).toBe(1);
  await page.getByRole('combobox', { name: 'Category', exact: true }).selectOption('sms');
  await expect(reminders).not.toBeVisible();
  for (const name of ['Upcoming and to follow up', 'Already received'])
    await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
  await expect(offers).toBeVisible();
  const sms = page
    .locator('details')
    .filter({ has: page.locator('summary').getByText('My SMS', { exact: true }) })
    // The page's « Filters » fold now names the chosen category in its summary.
    .filter({ hasNot: page.locator(':scope > summary').getByText('Filters', { exact: true }) });
  expect(smsReads).toHaveLength(0);
  await sms.locator(':scope > summary').click();
  await expect(
    sms.getByRole('paragraph').filter({ hasText: '<script>literal message</script>' })
  ).toBeVisible();
  expect(smsReads.at(-1)).toMatchObject({ query: 'été', sort: 'name' });
  await expect(sms.locator('time')).toContainText('12:30');
  // The section's own period folds too, under the page's.
  await openListFilters(sms, 'Filters');
  await sms.getByLabel('From (inclusive)', { exact: false }).fill('2026-11-02');
  await expect.poll(() => smsReads.at(-1)?.from_ts).toBe('2026-11-01T11:00:00.000Z');
  const before = smsReads.length;
  await sms.getByLabel('Until (exclusive)', { exact: false }).fill('2026-11-01');
  await expect(sms.getByRole('alert')).toBeVisible();
  expect(smsReads).toHaveLength(before);
  refusal = 'QUERY_TOO_BROAD';
  await sms.getByLabel('From (inclusive)', { exact: false }).fill('2026-10-31');
  await expect(
    sms.getByText('Search too broad. Add words, a sender or a date range.')
  ).toBeVisible();
  expect(smsReads.at(-1)?.from_ts).toBe('2026-10-30T11:00:00.000Z');
  expect(smsReads.at(-1)?.to_ts).toBe('2026-10-31T11:00:00.000Z');
  refusal = null;
  await sms.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(
    sms.getByRole('paragraph').filter({ hasText: '<script>literal message</script>' })
  ).toBeVisible();
  await expect(sms.locator('script')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await sms.evaluate(node => node.setAttribute('data-alert-a11y', ''));
  expect(
    (await new AxeBuilder({ page }).include('[data-alert-a11y]').analyze()).violations
  ).toEqual([]);
});
