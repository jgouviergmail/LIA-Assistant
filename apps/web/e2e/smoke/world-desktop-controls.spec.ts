import { test, expect, chatRoutes } from '../fixtures';
import type { Page } from '@playwright/test';
import { installInertWorldAdmission } from '../fixtures/world-session';
import en from '../../locales/en/translation.json';

async function enter(page: Page) {
  await page.goto('/en/dashboard/world');
  await page.locator('.world-admission input[type="checkbox"]').check();
  await page.locator('.world-admission button[type="submit"]').click();
  await expect(page.locator('[data-world-status="shared"]')).toBeVisible();
}

for (const width of [768, 1024, 1440])
  test(`desktop controls share one bottom row without overlap at ${width}px`, async ({
    page,
    authenticate,
  }) => {
    const user = await authenticate();
    await installInertWorldAdmission(page, user.id);
    await page.setViewportSize({ width, height: 900 });
    await enter(page);
    const actions = await page.locator('.world-session-strip').boundingBox();
    const tools = await page.locator('.world-bottom .world-tools').boundingBox();
    if (!actions || !tools) throw new Error('Missing game controls');
    expect(Math.abs(actions.y + actions.height / 2 - tools.y - tools.height / 2)).toBeLessThan(2);
    expect(actions.x + actions.width + 8).toBeLessThanOrEqual(tools.x);
    expect(tools.x + tools.width).toBeLessThanOrEqual(width);
  });

test('desktop peer conversation stays open while the focused scene moves and typing keeps its draft', async ({
  page,
  authenticate,
}) => {
  const user = await authenticate();
  const peer = '5010c2c2-4bd0-4d21-9c08-b4502db25001';
  await installInertWorldAdmission(page, user.id, {
    actors: [{ id: peer, alias: 'Camille', position: { x: 36, y: 34 }, facing: 1, walking: false }],
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await enter(page);
  await page.getByRole('button', { name: en.world.messages.action }).click();
  const dock = page.locator('[data-world-messages]');
  await dock.getByRole('navigation').getByRole('button').filter({ hasText: 'Camille' }).click();
  const field = dock.getByRole('textbox', { name: en.world.messages.message });
  await field.fill('An unsent private draft');
  const position = () =>
    page
      .locator('.world-minimap circle')
      .last()
      .evaluate(node => node.getAttribute('cx'));
  const beforeTyping = await position();
  await field.press('ArrowRight');
  expect(await position()).toBe(beforeTyping);
  const canvas = page.locator('canvas.world-canvas');
  await canvas.click({ position: { x: 180, y: 300 } });
  await expect(canvas).toBeFocused();
  const beforeWalking = await position();
  await page.keyboard.down('ArrowRight');
  try {
    await expect.poll(position).not.toBe(beforeWalking);
  } finally {
    await page.keyboard.up('ArrowRight');
  }
  await expect(dock).toBeVisible();
  await expect(field).toHaveValue('An unsent private draft');
});

test('desktop LIA conversation stays open while the focused scene moves and typing keeps its draft', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const user = await authenticate();
  await installInertWorldAdmission(page, user.id);
  await mockApi(chatRoutes([]));
  await page.setViewportSize({ width: 1440, height: 900 });
  await enter(page);
  await page.getByRole('button', { name: en.world.functions.talk, exact: true }).click();
  const dock = page.locator('[data-world-native-panel]');
  const field = dock.locator('textarea');
  await field.fill('An unsent question for LIA');
  const position = () =>
    page
      .locator('.world-minimap circle')
      .last()
      .evaluate(node => node.getAttribute('cx'));
  const beforeTyping = await position();
  await field.press('ArrowRight');
  expect(await position()).toBe(beforeTyping);
  const canvas = page.locator('canvas.world-canvas');
  await canvas.click({ position: { x: 180, y: 300 } });
  await expect(canvas).toBeFocused();
  const beforeWalking = await position();
  await page.keyboard.down('ArrowRight');
  try {
    await expect.poll(position).not.toBe(beforeWalking);
  } finally {
    await page.keyboard.up('ArrowRight');
  }
  await expect(dock).toBeVisible();
  await expect(field).toHaveValue('An unsent question for LIA');
});
