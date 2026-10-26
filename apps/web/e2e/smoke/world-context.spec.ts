/** Real canvas picking and contextual UI; transport is explicitly hermetic here. */
import { test, expect } from '../fixtures';
import type { Page } from '@playwright/test';
import { installInertWorldAdmission } from '../fixtures/world-session';
import { baseRoutes, sseDone } from '../fixtures/chat-approval';
import { WORLD } from '../../src/features/world/definition';
import { compileNavigation, isWalkable } from '../../src/features/world/navigation';
import en from '../../locales/en/translation.json';

async function enter(page: Page) {
  await page.goto('/en/dashboard/world');
  await page.locator('.world-admission input[type="checkbox"]').check();
  await page.getByRole('button', { name: en.world.session.enter, exact: true }).click();
  await expect(page.locator('[data-world-status="shared"]')).toBeVisible();
  await expect(page.getByRole('button', { name: en.world.messages.action })).toBeEnabled();
}
async function clickAt(
  page: Page,
  spawn: { x: number; y: number },
  at: { x: number; y: number },
  height: number
) {
  const canvas = page.locator('canvas.world-canvas');
  const box = await canvas.boundingBox();
  if (!box) throw new Error('No scene');
  await canvas.click({
    position: {
      x: box.width / 2 + (at.x - at.y - (spawn.x - spawn.y)) * 32 * 0.95,
      y: box.height / 2 + ((at.x + at.y - spawn.x - spawn.y) * 16 + 28 - height) * 0.95,
    },
  });
}

test('world: a visible person opens their own private conversation and retains recipient drafts', async ({
  page,
  authenticate,
  mockApi,
}, info) => {
  const user = await authenticate();
  const spawn = WORLD.spawn;
  const peer = {
    id: '5010c2c2-4bd0-4d21-9c08-b4502db25d72',
    alias: 'Camille',
    position: { x: spawn.x + 1, y: spawn.y + 2 },
    facing: 1,
    walking: false,
  };
  await installInertWorldAdmission(page, user.id, { spawn, actors: [peer] });
  await mockApi([
    {
      url: '**/api/v1/world/messages/read',
      json: { server_time: Date.now() / 1000, ttl_seconds: 1800, messages: [], truncated: false },
    },
  ]);
  await enter(page);
  const sends: string[] = [];
  page.on('request', request => {
    if (/\/world\/messages\/(send|translate)$/.test(request.url())) sends.push(request.url());
  });
  // The nameplate uses the same masked pixels as the visible character.
  await expect(async () => {
    await clickAt(page, spawn, peer.position, 83);
    await expect(page.getByRole('dialog', { name: peer.alias, exact: true })).toBeVisible({
      timeout: 1500,
    });
  }).toPass({ timeout: 15000 });
  await expect(page.getByRole('form', { name: 'Message to ' + peer.alias })).toBeVisible();
  const field = page.getByRole('textbox', { name: en.world.messages.message });
  await field.fill('Private unsent draft');
  await page.keyboard.press('Escape');
  await expect(page.locator('canvas.world-canvas')).toBeFocused();
  await page.getByRole('button', { name: en.world.messages.action }).click();
  await expect(field).toHaveValue('Private unsent draft');
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 390, height: 844 },
    { width: 320, height: 568 },
  ]) {
    await page.setViewportSize(viewport);
    await expect(field).toBeVisible();
    await expect(page.getByRole('log')).toBeVisible();
    const bounds = await page.getByRole('dialog').boundingBox();
    expect(bounds).not.toBeNull();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(viewport.width);
    expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(viewport.height);
    await page.screenshot({ path: info.outputPath('conversation-' + viewport.width + '.png') });
  }
  expect(sends).toEqual([]);
});

test('world: the engineering telescope approaches then prepares the localized weather request without sending', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const user = await authenticate();
  await mockApi(baseRoutes(null, sseDone));
  const telescope = WORLD.props.find(prop => prop.key === 'weather');
  if (!telescope) throw new Error('Missing engineering weather telescope');
  const spawn = {
    x: telescope.x + telescope.width / 2,
    y: Math.ceil(telescope.y + telescope.depth) + 0.5,
  };
  expect(isWalkable(compileNavigation(WORLD), spawn)).toBe(true);
  await installInertWorldAdmission(page, user.id, { spawn });
  await enter(page);
  const sends: string[] = [];
  page.on('request', request => {
    if (request.method() === 'POST' && request.url().includes('/agents/chat/stream'))
      sends.push(request.url());
  });
  // Focus the scene and use the nearby action: no menu or page navigation.
  const contextual = page.locator('.world-context-action');
  await expect(contextual).toHaveText(new RegExp(en.chat.slash.weather_label));
  await contextual.click();
  await expect(page.getByRole('dialog', { name: en.world.functions.talk })).toBeVisible();
  await expect(page.locator('textarea')).toHaveValue(en.chat.slash.weather_intent);
  expect(sends).toEqual([]);
  expect(new URL(page.url()).pathname).toBe('/en/dashboard/world');
});

test('world: solid wall pixels cannot select a person hidden behind them', async ({
  page,
  authenticate,
}, info) => {
  const user = await authenticate();
  const spawn = { x: 10.5, y: 15.5 };
  const peer = {
    id: '5010c2c2-4bd0-4d21-9c08-b4502db25d72',
    alias: 'Behind the library wall',
    position: { x: 6.5, y: 12.5 },
    facing: 1,
    walking: false,
  };
  await installInertWorldAdmission(page, user.id, { spawn, actors: [peer] });
  await enter(page);
  await clickAt(page, spawn, peer.position, 50);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.screenshot({ path: info.outputPath('solid-wall-picking.png') });
});
