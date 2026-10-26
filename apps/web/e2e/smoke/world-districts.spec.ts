import { test, expect } from '../fixtures';
import { installInertWorldAdmission } from '../fixtures/world-session';
import { frameWorldProp } from '../fixtures/world-scene-navigation';
import { WORLD } from '../../src/features/world/definition';
import en from '../../locales/en/translation.json';
import { revealWorldControls } from '../fixtures/world-admission';

test('world districts: named objects, contextual cursor and keyboard/mobile map without implicit actions', async ({
  page,
  authenticate,
}, info) => {
  const user = await authenticate();
  await installInertWorldAdmission(page, user.id);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/en/dashboard/world');
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: en.world.session.enter, exact: true }).click();
  const canvas = page.locator('canvas.world-canvas');
  await expect(canvas).toBeVisible();
  const actions: string[] = [];
  page.on('request', request => {
    if (
      request.method() === 'POST' &&
      /agents\/chat|world\/messages\/(send|translate)/.test(request.url())
    )
      actions.push(request.url());
  });
  const summary = page.locator('[data-world-place-menu]');
  await expect(summary).toHaveText(en.world.explore_places);
  for (const [key, label] of [
    ['news', en.chat.slash.news_label],
    ['phone', en.world.activities.call],
  ] as const) {
    const prop = WORLD.props.find(p => p.key === key);
    if (!prop) throw Error('Missing functional object');
    const point = await frameWorldProp(
      page,
      prop,
      id => en.world.zones[id as keyof typeof en.world.zones]
    );
    await page.mouse.move(point.x, point.y);
    await expect(page.getByRole('tooltip')).toHaveText(label);
    await expect(canvas).toHaveCSS('cursor', 'pointer');
    await page.screenshot({ path: info.outputPath(key + '-affordance.png') });
    await page.mouse.move(0, 0);
    await expect(page.getByRole('tooltip')).toHaveCount(0);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await revealWorldControls(page);
  await summary.focus();
  await page.keyboard.press('Enter');
  const directory = page.locator('.world-map-directory');
  await expect(directory).toBeVisible();
  await expect(directory.getByRole('menuitem')).toHaveCount(WORLD.zones.length);
  const rect = await directory.boundingBox();
  expect(rect).not.toBeNull();
  expect(rect!.x).toBeGreaterThanOrEqual(0);
  expect(rect!.x + rect!.width).toBeLessThanOrEqual(390);
  expect(rect!.y + rect!.height).toBeLessThanOrEqual(844);
  for (const item of await directory.getByRole('menuitem').all()) await item.click({ trial: true });
  await directory.getByRole('menuitem').first().scrollIntoViewIfNeeded();
  await page.screenshot({ path: info.outputPath('places-phone.png') });
  await directory.getByRole('menuitem', { name: en.world.zones.cafeteria, exact: true }).click();
  await expect(directory).not.toBeVisible();
  await expect(summary).toBeFocused();
  expect(actions).toEqual([]);
});
