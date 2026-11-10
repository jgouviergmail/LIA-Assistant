/** Civil-time display intent survives a boundary, native editing and reload. */
import { test, expect } from '../fixtures';

test('automatic display follows account time, saves a pair and leaves on manual choice', async ({
  page,
  authenticate,
  mockApi,
}) => {
  test.setTimeout(240_000);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.clock.install({ time: new Date('2026-11-08T19:59:45Z') });
  const account = await authenticate({
    theme: 'auto',
    timezone: 'UTC',
    voice_enabled: false,
    theme_light_start_minute: 420,
    theme_dark_start_minute: 1200,
  });
  const patches: unknown[] = [];
  await mockApi([
    {
      url: `**/api/v1/users/${account.id}`,
      method: 'PATCH',
      handler: async route => {
        const patch: unknown = route.request().postDataJSON();
        patches.push(patch);
        if (patch && typeof patch === 'object') Object.assign(account, patch);
        await route.fulfill({ json: account });
      },
    },
  ]);
  await page.goto('/en/dashboard/settings?section=theme', { timeout: 180_000 });
  const section = page.locator('#settings-section-theme');
  await expect(section.getByRole('radio', { name: 'Automatic', exact: true })).toBeChecked();
  await expect(page.locator('html')).not.toHaveClass(/dark/);
  await page.clock.fastForward(30_000);
  await expect(page.locator('html')).toHaveClass(/dark/);
  await expect(page.locator('html')).toHaveAttribute('data-oled', '');
  expect(patches).toHaveLength(0);

  await section.getByLabel('Light mode starts').fill('08:15');
  await section.getByLabel('Absolute black starts').fill('21:45');
  await section.getByRole('button', { name: 'Save', exact: true }).click();
  await expect
    .poll(() => patches)
    .toContainEqual({ theme_light_start_minute: 495, theme_dark_start_minute: 1305 });
  await expect(page.locator('html')).not.toHaveClass(/dark/);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true
  );
  await page.reload();
  await expect(section.getByLabel('Light mode starts')).toHaveValue('08:15');
  await expect(section.getByRole('radio', { name: 'Automatic', exact: true })).toBeChecked();
  await section.getByText('Light', { exact: true }).click();
  await expect.poll(() => patches).toContainEqual({ theme: 'light' });
  await page.clock.fastForward(3 * 60 * 60 * 1000);
  await expect(page.locator('html')).not.toHaveClass(/dark/);
});
