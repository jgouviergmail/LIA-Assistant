/** Capture the real World scene with the existing inert authority and fictional people. */
import type { Page } from '@playwright/test';
import { installInertWorldAdmission } from '../fixtures/world-session';
import { registerRoutes, idleNotificationStream } from '../fixtures/api-mock';
import { publicScreenshotRoutes } from './public-screenshot-data';
import { WORLD } from '../../src/features/world/definition';

export async function captureWorld(page: Page, baseUrl: string, output: string) {
  const unexpected: string[] = [];
  const errors: string[] = [];
  const origin = new URL(baseUrl).origin;
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin || url.pathname.startsWith('/api/')) {
      unexpected.push(url.origin === origin ? url.pathname : url.origin);
      await route.abort();
    } else await route.continue();
  });
  await registerRoutes(page, [...publicScreenshotRoutes(), idleNotificationStream]);
  const ownerId = '00000000-0000-4000-8000-000000000001';
  const world = await installInertWorldAdmission(page, ownerId, {
    actors: [
      {
        id: '00000000-0000-4000-8000-000000000002',
        alias: 'Morgan',
        position: { x: WORLD.spawn.x + 2, y: WORLD.spawn.y + 2 },
        facing: 1,
        walking: false,
      },
      {
        id: '00000000-0000-4000-8000-000000000003',
        alias: 'Sam',
        position: { x: WORLD.spawn.x - 3, y: WORLD.spawn.y + 1 },
        facing: 3,
        walking: false,
      },
    ],
  });
  await page
    .context()
    .addCookies([
      {
        name: 'lia_session',
        value: 'fictional-world-capture',
        domain: new URL(baseUrl).hostname,
        path: '/',
      },
    ]);
  await page.addInitScript(() => {
    localStorage.setItem('theme', 'light');
    localStorage.setItem(
      'lia_eyes_widget_prefs',
      JSON.stringify({
        state: { visible: false, style: 'bip', size: 'm', position: null, landingPosition: null },
        version: 0,
      })
    );
  });
  await page.goto(`${baseUrl}/en/dashboard/world`, { waitUntil: 'domcontentloaded' });
  await page.locator('.world-admission input[type="checkbox"]').check();
  await page.locator('.world-admission button[type="submit"]').click();
  await page.locator('[data-world-status="shared"]').waitFor({ timeout: 30000 });
  await world.afterSnapshots(20);
  await page.evaluate(() => document.fonts.ready);
  await page.mouse.move(0, 0);
  await page.screenshot({
    path: `${output}/lia-world.jpg`,
    type: 'jpeg',
    quality: 95,
    animations: 'disabled',
  });
  if (unexpected.length || errors.length) throw new Error(JSON.stringify({ unexpected, errors }));
  return {
    unexpected,
    errors,
    route: '/en/dashboard/world',
    viewport: page.viewportSize(),
    data: 'Real World canvas and controls; fictional people and inert local session authority. No shared server, real account or external action.',
  };
}
