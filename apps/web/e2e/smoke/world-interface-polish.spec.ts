import { test, expect } from '@playwright/test';
import { installApiCatchAll, registerRoutes } from '../fixtures/api-mock';
import { dashboardShellMocks } from '../fixtures/dashboard-shell';
import { makeTestUser } from '../fixtures/test-user';
import { installOfflineFonts } from '../fixtures/offline-fonts';
import { installInertWorldAdmission } from '../fixtures/world-session';
import { enterWorld } from '../fixtures/world-admission';
import { WORLD } from '../../src/features/world/definition';

for (const theme of ['light', 'dark'] as const)
  test('places remain readable and keyboard navigable in ' + theme, async ({ page }, info) => {
    await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    await installOfflineFonts(page);
    await installApiCatchAll(page);
    const user = makeTestUser();
    await registerRoutes(page, [...dashboardShellMocks, { url: '**/api/v1/auth/me', json: user }]);
    await installInertWorldAdmission(page, user.id);
    await page.goto('/fr/dashboard/world', { waitUntil: 'domcontentloaded' });
    await enterWorld(page);
    await expect(page.locator('canvas.world-canvas')).toBeVisible();
    await expect(page.locator('html')).toHaveClass(new RegExp('(^| )' + theme + '( |$)'));
    const trigger = page.getByRole('button', { name: 'Explorer les lieux', exact: true });
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
      if (width === 390)
        await page.getByRole('button', { name: 'Commandes du monde', exact: true }).click();
      await trigger.focus();
      await page.keyboard.press('Enter');
      const menu = page.getByRole('menu', { name: 'Explorer les lieux', exact: true });
      await expect(menu).toBeVisible();
      await expect(menu.getByRole('menuitem')).toHaveCount(WORLD.zones.length);
      for (const focused of [false, true]) {
        await page.mouse.move(0, 0);
        if (focused) await page.keyboard.press('ArrowDown');
        const colors = await menu.evaluate((element, highlighted) => {
          const item = highlighted
            ? element.querySelector('[role="menuitem"][data-highlighted]')
            : element.querySelector('[role="menuitem"]:not([data-highlighted])');
          if (!item) throw new Error('No directory item');
          const style = getComputedStyle(item);
          const canvas = document.createElement('canvas');
          canvas.width = 1;
          canvas.height = 1;
          const c = canvas.getContext('2d');
          if (!c) throw new Error('No colour conversion');
          const rgb = (value: string) => {
            c.clearRect(0, 0, 1, 1);
            c.fillStyle = value;
            c.fillRect(0, 0, 1, 1);
            return [...c.getImageData(0, 0, 1, 1).data];
          };
          let surface: Element | null = item;
          while (surface && rgb(getComputedStyle(surface).backgroundColor)[3] < 250)
            surface = surface.parentElement;
          if (!surface) throw new Error('No opaque menu surface');
          const fg = rgb(style.color),
            bg = rgb(getComputedStyle(surface).backgroundColor);
          const luminance = (values: number[]) =>
            values.slice(0, 3).reduce((sum, v, i) => {
              const n = v / 255;
              return (
                sum +
                (n <= 0.04045 ? n / 12.92 : ((n + 0.055) / 1.055) ** 2.4) *
                  [0.2126, 0.7152, 0.0722][i]
              );
            }, 0);
          const f = luminance(fg),
            b = luminance(bg);
          return {
            foreground: style.color,
            background: getComputedStyle(surface).backgroundColor,
            contrast: (Math.max(f, b) + 0.05) / (Math.min(f, b) + 0.05),
          };
        }, focused);
        console.info('directory contrast', theme, width, focused, colors);
        expect(colors.contrast).toBeGreaterThanOrEqual(4.5);
      }
      const bounds = await menu.boundingBox();
      if (!bounds) throw new Error('No menu bounds');
      expect(bounds.x).toBeGreaterThanOrEqual(0);
      expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
      await page.screenshot({ path: info.outputPath(theme + '-' + width + '-places.png') });
      await page.keyboard.press('Escape');
      await expect(menu).not.toBeVisible();
      await expect(trigger).toBeFocused();
    }
  });
