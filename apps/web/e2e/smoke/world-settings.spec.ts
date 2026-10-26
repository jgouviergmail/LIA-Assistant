/** Activities and preferences remain separate, operable and private in the world. */
import { test, expect } from '../fixtures';
import { installInertWorldAdmission } from '../fixtures/world-session';
import en from '../../locales/en/translation.json';
import { revealWorldControls } from '../fixtures/world-admission';

test('world: settings are separate from activities on desktop and touch', async ({
  page,
  authenticate,
}, info) => {
  const user = await authenticate();
  await installInertWorldAdmission(page, user.id);
  await page.goto('/en/dashboard/world');
  await page.locator('.world-admission input[type="checkbox"]').check();
  await page.getByRole('button', { name: en.world.session.enter, exact: true }).click();
  const activities = page.getByRole('button', { name: en.world.functions.title, exact: true });
  const settings = page.getByRole('button', { name: en.world.settings.application, exact: true });
  const scene = page.locator('canvas.world-canvas');
  const writes: string[] = [];
  page.on('request', request => {
    if (
      request.method() !== 'GET' &&
      /\/api\/v1\/(agents|users|memories|interests|llm)/.test(request.url())
    )
      writes.push(new URL(request.url()).pathname);
  });
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 390, height: 844 },
    { width: 320, height: 568 },
  ]) {
    await page.setViewportSize(viewport);
    await expect(scene).toBeVisible();
    await revealWorldControls(page);
    await activities.click();
    await page.getByRole('menuitem', { name: en.world.functions.title, exact: true }).click();
    let dialog = page.getByRole('dialog');
    await expect(
      dialog.getByRole('button', { name: en.memories.settings.title, exact: true })
    ).toBeVisible();
    await expect(
      dialog.getByRole('button', { name: en.settings.language.title, exact: true })
    ).toHaveCount(0);
    await page.keyboard.press('Escape');
    await expect(activities).toBeFocused();
    await settings.click();
    dialog = page.getByRole('dialog', { name: en.world.settings.application, exact: true });
    await expect(dialog).toBeVisible();
    await expect(
      dialog.getByRole('button', { name: en.settings.language.title, exact: true })
    ).toBeVisible();
    await expect(
      dialog.getByRole('button', { name: en.memories.settings.title, exact: true })
    ).toHaveCount(0);
    await page.screenshot({ path: info.outputPath('settings-' + viewport.width + '.png') });
    await page.keyboard.press('Escape');
    await expect(settings).toBeFocused();
  }
  expect(writes).toEqual([]);
});
