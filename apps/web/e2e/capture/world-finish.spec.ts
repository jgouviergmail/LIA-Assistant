import { test, expect } from '@playwright/test';
import { installApiCatchAll, registerRoutes } from '../fixtures/api-mock';
import { dashboardShellMocks } from '../fixtures/dashboard-shell';
import { makeTestUser } from '../fixtures/test-user';
import { installOfflineFonts } from '../fixtures/offline-fonts';
import { installInertWorldAdmission } from '../fixtures/world-session';
import { enterWorld } from '../fixtures/world-admission';
import { WORLD, onSite } from '../../src/features/world/definition';

for (const phase of ['day', 'night'] as const)
  test('world finishing review ' + phase, async ({ page }, info) => {
    await installOfflineFonts(page);
    await installApiCatchAll(page);
    const user = makeTestUser();
    await registerRoutes(page, [...dashboardShellMocks, { url: '**/api/v1/auth/me', json: user }]);
    await installInertWorldAdmission(page, user.id);
    await registerRoutes(page, [
      { url: '**/api/v1/world-proof/me', json: { owner_id: user.id, language: 'fr' } },
      {
        url: '**/api/v1/world/environment',
        json: {
          server_time:
            Date.parse(phase === 'day' ? '2026-10-25T11:00:00Z' : '2026-10-25T01:00:00Z') / 1000,
          timezone: 'Europe/Paris',
          weather: null,
        },
      },
    ]);
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/fr/world-preview?shared=1&resume=1', { waitUntil: 'domcontentloaded' });
    await enterWorld(page);
    const canvas = page.locator('canvas.world-canvas');
    await expect(canvas).toBeVisible();
    await page
      .getByRole('combobox', { name: /Éclairage de démonstration/ })
      .selectOption(phase === 'day' ? 'noon' : 'night');
    await expect(page.locator('.world-prototype')).toHaveAttribute(
      'data-world-phase',
      phase === 'day' ? 'noon' : 'night'
    );
    const map = page.getByRole('button', { name: /^Carte du monde/ });
    const targets = [
      ...WORLD.zones.map(z => ({ id: z.id, x: z.x + z.width / 2, y: z.y + z.height / 2 })),
      { id: 'potager', ...onSite({ x: 8, y: 66 }) },
      { id: 'trees', ...onSite({ x: 12, y: 80 }) },
      { id: 'pond', ...onSite({ x: 21, y: 70 }) },
    ];
    for (const target of targets) {
      const bounds = await map.boundingBox();
      if (!bounds) throw new Error('Missing minimap');
      await map.click({
        position: {
          x:
            ((target.x - target.y + WORLD.height + 4) / (WORLD.width + WORLD.height + 8)) *
            bounds.width,
          y:
            (((target.x + target.y) / 2 + 4) / ((WORLD.width + WORLD.height) / 2 + 8)) *
            bounds.height,
        },
      });
      await page.waitForTimeout(350);
      await canvas.screenshot({ path: info.outputPath(phase + '-' + target.id + '.png') });
    }
    const crystal = WORLD.props.find(prop => prop.kind === 'crystal');
    if (!crystal) throw new Error('No authored crystal');
    const mapBounds = await map.boundingBox();
    if (!mapBounds) throw new Error('No map bounds');
    const cx = crystal.x + crystal.width / 2,
      cy = crystal.y + crystal.depth / 2;
    await map.click({
      position: {
        x: ((cx - cy + WORLD.height + 4) / (WORLD.width + WORLD.height + 8)) * mapBounds.width,
        y: (((cx + cy) / 2 + 4) / ((WORLD.width + WORLD.height) / 2 + 8)) * mapBounds.height,
      },
    });
    const box = await canvas.boundingBox();
    if (!box) throw new Error('No canvas bounds');
    await canvas.hover({ position: { x: box.width / 2, y: box.height / 2 - 48 } });
    await expect(canvas).toHaveCSS('cursor', 'pointer');
    await canvas.screenshot({ path: info.outputPath(phase + '-crystal-footprint.png') });
    await page.mouse.move(0, 0);
    await page.getByRole('button', { name: 'Performances', exact: true }).click();
    await page.waitForTimeout(500);
    console.info('render-budget', phase, await page.locator('.world-metrics').innerText());
    const texture = Number(
      (await page.locator('.world-metrics dd').nth(3).innerText()).split(' ')[0].replace(',', '.')
    );
    expect(texture).toBeLessThanOrEqual(128);
    await page.getByRole('button', { name: 'Fermer les performances', exact: true }).click();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(600);
    await page.screenshot({ path: info.outputPath(phase + '-mobile.png') });
    expect(errors).toEqual([]);
  });
