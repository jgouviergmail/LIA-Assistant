/** A pending write must preserve the keyboard user's actual browser focus. */
import { test, expect } from '../fixtures';
import type { Page } from '@playwright/test';
import { installInertWorldAdmission } from '../fixtures/world-session';
import { WORLD } from '../../src/features/world/definition';
import en from '../../locales/en/translation.json';

async function holdWrite(page: Page, endpoint: string, status: number) {
  let release: () => void = () => {};
  const pending = new Promise<void>(resolve => {
    release = resolve;
  });
  let writes = 0;
  await page.route('**/api/v1/world/' + endpoint, async route => {
    if (!['POST', 'PUT'].includes(route.request().method())) return route.fallback();
    writes++;
    await pending;
    await route.fulfill({ status, json: { detail: 'Controlled write failure' } });
  });
  return { release, count: () => writes };
}

async function enter(page: Page) {
  await page.goto('/en/dashboard/world');
  await page.locator('input[name="world-presence-consent"]').check();
  await page.locator('.world-admission button[type="submit"]').click();
  await expect(page.locator('[data-world-status="shared"]')).toBeVisible();
}

test('world avatar: pending save keeps the focused submit and appearance through failure', async ({
  page,
  authenticate,
}) => {
  const user = await authenticate();
  await installInertWorldAdmission(page, user.id);
  const pending = await holdWrite(page, 'avatar', 503);
  try {
    await page.goto('/en/dashboard/world');
    const hair = page.getByRole('combobox', { name: en.world.avatar.hair, exact: true });
    await hair.selectOption('long');
    await page.locator('input[name="world-presence-consent"]').check();
    const submit = page.locator('.world-admission button[type="submit"]');
    await submit.focus();
    await page.keyboard.press('Enter');
    await expect(submit).toHaveAttribute('aria-disabled', 'true');
    await expect(submit).toBeFocused();
    await expect(submit).toHaveJSProperty('disabled', false);
    await page.keyboard.press('Enter');
    expect(pending.count()).toBe(1);
    await hair.focus();
    await page.keyboard.press('Home');
    await expect(hair).toHaveValue('long');
    await submit.focus();
    pending.release();
    await expect(page.getByRole('alert')).toBeVisible();
    await expect(submit).toBeFocused();
    await expect(hair).toHaveValue('long');
  } finally {
    pending.release();
  }
});

test('world home: pending save preserves focus and palette after a revision conflict', async ({
  page,
  authenticate,
}) => {
  const user = await authenticate();
  await installInertWorldAdmission(page, user.id);
  await enter(page);
  const pending = await holdWrite(page, 'home', 409);
  try {
    await page.getByRole('button', { name: en.world.home.open, exact: true }).click();
    const dialog = page.getByRole('dialog', { name: en.world.home.title, exact: true });
    const teal = dialog.getByRole('radio', { name: en.world.home.palettes.teal, exact: true });
    await teal.check();
    const submit = dialog.getByRole('button', { name: en.world.home.save, exact: true });
    await submit.focus();
    await page.keyboard.press('Enter');
    await expect(submit).toHaveAttribute('aria-disabled', 'true');
    await expect(submit).toBeFocused();
    await expect(submit).toHaveJSProperty('disabled', false);
    await page.keyboard.press('Enter');
    expect(pending.count()).toBe(1);
    await expect(teal).toHaveJSProperty('disabled', false);
    pending.release();
    await expect(dialog.getByRole('alert')).toHaveText(en.world.home.conflict);
    await expect(submit).toBeFocused();
    await expect(teal).toBeChecked();
  } finally {
    pending.release();
  }
});

for (const focus of ['message', 'send'] as const) {
  test(
    'world messages: sending preserves ' + focus + ' focus and blocks duplicate keyboard sends',
    async ({ page, authenticate }) => {
      const user = await authenticate();
      await installInertWorldAdmission(page, user.id, {
        actors: [
          {
            id: '5010c2c2-4bd0-4d21-9c08-b4502db25001',
            alias: 'Camille',
            position: { x: WORLD.spawn.x + 1, y: WORLD.spawn.y + 2 },
            facing: 1,
            walking: false,
          },
        ],
      });
      await enter(page);
      const pending = await holdWrite(page, 'messages/send', 400);
      try {
        await page.getByRole('button', { name: en.world.messages.action, exact: true }).click();
        await page.getByRole('button', { name: /^Camille/ }).click();
        const message = page.getByRole('textbox', { name: en.world.messages.message, exact: true });
        await message.fill('Keep this draft');
        await page.getByRole('checkbox', { name: en.world.messages.consent, exact: true }).check();
        const send = page.getByRole('button', { name: en.world.messages.send, exact: true });
        const control = focus === 'message' ? message : send;
        await control.focus();
        await page.keyboard.press('Enter');
        await expect(send).toHaveAttribute('aria-disabled', 'true');
        await expect(message).toHaveAttribute('readonly', '');
        await expect(control).toBeFocused();
        await page.keyboard.press('Enter');
        expect(pending.count()).toBe(1);
        pending.release();
        await expect(message).not.toHaveAttribute('readonly');
        await expect(control).toBeFocused();
        await expect(message).toHaveValue('Keep this draft');
      } finally {
        pending.release();
      }
    }
  );
}
