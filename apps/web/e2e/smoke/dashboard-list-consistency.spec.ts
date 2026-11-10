/** Shared page landmarks, touch targets and reflow across the seven dashboard doors. */
import AxeBuilder from '@axe-core/playwright';
import { test, expect, idleNotificationStream, type MockRoute } from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';
import { relationsData } from '../fixtures/relations';
import fr from '../../locales/fr/translation.json';

const emptySms = {
  items: [],
  total: 0,
  revision: 1,
  as_of: '2026-11-01T12:00:00Z',
  next_cursor: null,
};
const routes: MockRoute[] = [
  idleNotificationStream,
  ...relationsData,
  { url: '**/api/v1/habits/presence', method: 'POST', status: 204 },
  { url: '**/api/v1/agents/runs/active', json: { active: false } },
  {
    url: '**/api/v1/system-settings/debug-panel-status',
    json: { enabled: false, user_access_available: false },
  },
  { url: '**/api/v1/meetings/active', status: 204 },
  { url: '**/api/v1/notifications/broadcasts/unread', json: { broadcasts: [] } },
  {
    url: '**/api/v1/config',
    json: {
      ...appConfig,
      features: {
        ...appConfig.features,
        sms_enabled: true,
        meetings_enabled: true,
        meetings_import_enabled: true,
        habits_enabled: true,
        workboard_enabled: false,
      },
    },
  },
  { url: '**/api/v1/meetings*', json: { items: [], total: 0, limit: 20, offset: 0 } },
  { url: '**/api/v1/sms/senders*', json: emptySms },
  { url: '**/api/v1/sms/search', json: emptySms },
  { url: '**/api/v1/sms/blocked-senders*', json: { ...emptySms, blocks: [] } },
  {
    url: '**/api/v1/notifications/hub-counts',
    json: { reminders: 0, scheduled: 0, interests: 0, offers: 0, sms: 0 },
  },
  {
    url: '**/api/v1/habits/proposals*',
    json: { proposals: [], total: 0, learning_enabled: false },
  },
];

const pages = [
  { path: 'relations', title: fr.relations.title, collection: true },
  { path: 'sms', title: fr.sms.title, collection: true },
  { path: 'meetings', title: fr.meetings.list.title, collection: true },
  { path: 'spaces', title: fr.spaces.title, collection: true },
  { path: 'notifications', title: fr.notifications_hub.title, collection: true },
  { path: 'settings', title: fr.settings.title, collection: false },
  { path: 'faq', title: fr.faq.title, collection: false },
];

for (const item of pages) {
  test(`consistent heading and controls on ${item.path}`, async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    test.setTimeout(120_000);
    const errors: string[] = [];
    const unmocked: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('response', response => {
      if (response.status() === 501) unmocked.push(new URL(response.url()).pathname);
    });
    await authenticate({ language: 'fr', timezone: 'Europe/Paris' });
    await mockApi(routes);
    await page.setViewportSize({ width: 390, height: 900 });
    await page.goto(`/fr/dashboard/${item.path}`);
    const main = page.getByRole('main');
    const heading = main.getByRole('heading', { level: 1, name: item.title, exact: true });
    await expect(heading).toBeVisible();
    const header = heading.locator('xpath=ancestor::header[1]');
    const search = main.getByRole('searchbox').first();
    if (item.collection) await expect(search).toBeVisible();

    for (const width of [320, 390, 768, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      await expect(heading).toHaveCSS('font-size', width < 640 ? '24px' : '30px');
      await expect(heading).toHaveCSS('font-weight', '600');
      const icon = heading.locator(':scope > [aria-hidden="true"]');
      await expect(icon).toBeVisible();
      await expect(icon).toHaveCSS('width', width < 640 ? '28px' : '32px');
      const iconBox = await icon.boundingBox();
      const titleBox = await heading.locator(':scope > span').last().boundingBox();
      if (!iconBox || !titleBox) throw new Error('The heading must have a visible icon and title');
      expect(iconBox.x + iconBox.width).toBeLessThanOrEqual(titleBox.x);

      // Header actions remain whole, reachable and large enough to tap.
      for (const action of await header.locator('button, a').all()) {
        const box = await action.boundingBox();
        if (!box) throw new Error('A page action must remain visible');
        expect(box.height).toBeGreaterThanOrEqual(44);
        expect(box.x).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width).toBeLessThanOrEqual(width);
      }
      if (item.collection) {
        await expect(search).toHaveCSS('height', '44px');
        const searchBox = await search.boundingBox();
        const headerBox = await header.boundingBox();
        if (!searchBox || !headerBox)
          throw new Error('A collection must have its search below its header');
        expect(searchBox.y).toBeGreaterThanOrEqual(headerBox.y + headerBox.height);
        expect(Math.abs(searchBox.x - headerBox.x)).toBeLessThan(1);
        await expect(main.getByRole('button', { name: 'Rechercher', exact: true })).toHaveCount(0);
        const fields = main.locator('select, input[type="date"]');
        let controlLeft: number | undefined;
        for (const field of await fields.all()) {
          if (!(await field.isVisible())) continue;
          const box = await field.boundingBox();
          if (!box) throw new Error('A filter must have a visible box');
          expect(box.height).toBe(44);
          expect(box.y).toBeGreaterThanOrEqual(searchBox.y + searchBox.height);
          if (width < 640) {
            if (controlLeft !== undefined) expect(box.x).toBe(controlLeft);
            controlLeft = box.x;
          }
        }
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true
      );
      if (width === 390 || width === 1280) {
        await page.screenshot({
          path: testInfo.outputPath(`${item.path}-${width}.png`),
          fullPage: true,
        });
      }
    }

    if (item.path === 'relations') {
      await expect(main.getByRole('button', { name: 'Sur LIA', exact: true })).toBeVisible();
      await expect(main.getByRole('button', { name: 'En sommeil', exact: true })).toBeVisible();
      await expect(main.getByRole('combobox')).toBeVisible();
    }
    if (item.path === 'spaces') {
      await expect(main.getByRole('button', { name: 'Géré par LIA', exact: true })).toBeVisible();
      await expect(main.getByRole('combobox')).toHaveCount(2);
    }
    await header.evaluate(node => node.setAttribute('data-heading-a11y', ''));
    expect(
      (await new AxeBuilder({ page }).include('[data-heading-a11y]').analyze()).violations
    ).toEqual([]);
    expect(errors).toEqual([]);
    expect(unmocked).toEqual([]);
  });
}
