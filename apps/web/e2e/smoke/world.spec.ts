/** Real canvas/input proof through the hermetic, provider-blocking app harness. */
import { test, expect } from '../fixtures';
import type { Page } from '@playwright/test';
import { revealWorldControls } from '../fixtures/world-admission';
import { scanPage } from '../a11y/scan';
import { appConfig } from '../fixtures/dashboard-shell';
import { enableWorld, installInertWorldAdmission } from '../fixtures/world-session';
import fr from '../../locales/fr/translation.json';

async function actorPosition(page: Page) {
  const marker = page.locator('.world-minimap circle').last();
  return { x: Number(await marker.getAttribute('cx')), y: Number(await marker.getAttribute('cy')) };
}

async function actorAtRest(page: Page) {
  await expect
    .poll(async () => {
      const before = await actorPosition(page);
      await page.waitForTimeout(400);
      const after = await actorPosition(page);
      return before.x === after.x && before.y === after.y;
    })
    .toBe(true);
  return actorPosition(page);
}

async function enterInertWorld(page: Page) {
  await page.locator('.world-admission input[type="checkbox"]').check();
  await page.locator('.world-admission button[type="submit"]').click();
}

test('world: shared header fits all eight destinations in all six languages', async ({
  page,
  authenticate,
  mockApi,
  browserName,
}) => {
  test.skip(
    browserName !== 'chromium',
    'Responsive shell matrix; world interactions cover all engines'
  );
  await authenticate();
  await mockApi([
    {
      url: '**/api/v1/config',
      json: {
        ...appConfig,
        features: { ...appConfig.features, meetings_enabled: true, world_enabled: true },
      },
    },
  ]);
  for (const lng of ['fr', 'en', 'de', 'es', 'it', 'zh']) {
    await page.setViewportSize({ width: 1536, height: 900 });
    await page.goto(`/${lng}/dashboard/world`);
    await expect(page.locator('.world-admission')).toBeVisible();
    const banner = page.getByRole('banner');
    const nav = banner.getByRole('navigation');
    await expect(nav.getByRole('link')).toHaveCount(8);
    for (const width of [1536, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      const row = await nav.boundingBox();
      if (!row) throw new Error('Missing shared navigation');
      for (const button of await banner.getByRole('button').all()) {
        if (!(await button.isVisible())) continue;
        const bounds = await button.boundingBox();
        if (!bounds) throw new Error('Missing visible header control');
        expect(
          Math.min(row.x + row.width, bounds.x + bounds.width) - Math.max(row.x, bounds.x),
          `${lng} at ${width}px overlaps a header control`
        ).toBeLessThanOrEqual(0);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true
      );
    }
  }
});

test('world: anonymous preview follows its server deployment guard without exposing account data', async ({
  page,
  mockApi,
}) => {
  await mockApi([{ url: '**/api/v1/auth/me', status: 401, json: { detail: 'Not authenticated' } }]);
  const response = await page.goto('/en/world-preview');
  if (response?.status() === 404) {
    await expect(page.locator('canvas.world-canvas')).toHaveCount(0);
    return;
  }
  expect(response?.status()).toBe(200);
  await expect(page.locator('canvas.world-canvas')).toBeVisible();
  await expect(page).toHaveURL(/\/en\/world-preview$/);
  expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight)).toBe(
    true
  );
  await page.getByRole('button', { name: 'How to explore', exact: true }).click();
  await expect(page.getByText('Local exploration · 0 LLM tokens', { exact: true })).toBeVisible();
});

test('world: desktop walking, zoom, camera, LIA, help and frame evidence', async ({
  page,
  authenticate,
}, info) => {
  const user = await authenticate();
  await installInertWorldAdmission(page, user.id);
  await page.goto('/fr/dashboard/world');
  await enterInertWorld(page);
  const canvas = page.getByLabel('Monde isométrique. Place le focus ici pour te déplacer.');
  await expect(canvas).toBeVisible();
  await expect(page.getByRole('heading', { name: fr.world.title, exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Performances', exact: true }).click();
  await expect
    .poll(async () =>
      Number((await page.locator('[data-world-fps]').innerText()).replace(',', '.'))
    )
    .toBeGreaterThan(0);
  const start = await actorPosition(page);
  await canvas.focus();
  await page.keyboard.down('ArrowRight');
  await page.waitForTimeout(600);
  await page.keyboard.up('ArrowRight');
  await expect.poll(async () => (await actorPosition(page)).x).toBeGreaterThan(start.x + 0.3);
  const keyboardPosition = await actorAtRest(page);
  const bounds = await canvas.boundingBox();
  if (!bounds) throw new Error('World viewport is unavailable');
  // Walk down the clear central aisle. The previous fixed rightward pixel
  // could pick autonomous LIA, correctly opening his menu instead of walking.
  const ground = {
    x: bounds.width / 2 - 8 * 32 * 0.95,
    y: bounds.height / 2 + (8 * 16 + 28) * 0.95,
  };
  await canvas.hover({ position: ground });
  await page.waitForTimeout(150); // Bounded 100ms scene-hover sampling.
  expect(await canvas.evaluate(element => element.style.cursor)).not.toBe('pointer');
  await canvas.click({ position: ground });
  await expect
    .poll(async () => {
      const at = await actorPosition(page);
      return Math.hypot(at.x - keyboardPosition.x, at.y - keyboardPosition.y);
    })
    .toBeGreaterThan(0.1);
  const afterWalk = await actorAtRest(page);
  const beforeZoom = await page.locator('[data-world-zoom]').innerText();
  await page.getByRole('button', { name: 'Zoomer', exact: true }).click();
  await expect(page.locator('[data-world-zoom]')).not.toHaveText(beforeZoom);
  await expect.poll(() => actorPosition(page)).toEqual(afterWalk);
  const minimap = page.getByRole('button', { name: /^Carte du monde/ });
  await minimap.click({ position: { x: 35, y: 25 } });
  await expect(page.getByRole('button', { name: 'Suivre mon personnage' })).toHaveAttribute(
    'aria-pressed',
    'false'
  );
  await expect.poll(() => actorPosition(page)).toEqual(afterWalk);
  await page.getByRole('button', { name: 'Suivre mon personnage' }).click();
  await page.getByRole('button', { name: 'Appeler LIA ou lui faire reprendre sa ronde' }).click();
  await expect(
    page.getByRole('button', { name: 'Appeler LIA ou lui faire reprendre sa ronde' })
  ).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'Comment explorer' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(canvas).toBeFocused();
  await page.waitForTimeout(3500);
  await page.screenshot({ path: info.outputPath('world-desktop.png'), fullPage: true });
  await info.attach('world-performance', {
    body: JSON.stringify({
      profile: 'desktop browser, not a physical phone',
      viewport: page.viewportSize(),
      fps: await page.locator('[data-world-fps]').innerText(),
      frameP95: await page.locator('[data-world-frame]').innerText(),
      renderP95: await page.locator('[data-world-render]').innerText(),
    }),
    contentType: 'application/json',
  });
});

test.describe('world: mobile layout and pointer controls', () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true });
  test('keeps the scene, minimap and controls usable at phone sizes', async ({
    page,
    authenticate,
  }, info) => {
    const user = await authenticate();
    await installInertWorldAdmission(page, user.id);
    await page.goto('/en/dashboard/world');
    await enterInertWorld(page);
    const canvas = page.getByLabel('Isometric world. Focus here to move.');
    await expect(canvas).toBeVisible();
    const right = page.locator('.world-joystick');
    await expect(right).toBeVisible();
    const before = await actorPosition(page);
    await right.hover();
    await page.mouse.down();
    const stick = await right.boundingBox();
    if (!stick) throw new Error('Missing joystick');
    await page.mouse.move(stick.x + stick.width / 2 + 30, stick.y + stick.height / 2);
    await page.waitForTimeout(600);
    await page.mouse.up();
    await expect.poll(async () => (await actorPosition(page)).x).toBeGreaterThan(before.x + 0.3);
    await page.getByRole('button', { name: 'World controls', exact: true }).click();
    await page.getByRole('button', { name: 'How to explore', exact: true }).click();
    await page.getByRole('combobox', { name: 'Graphics quality' }).selectOption('low');
    await page.getByRole('button', { name: 'Explore', exact: true }).click();
    await page.getByRole('button', { name: 'Performance', exact: true }).click();
    await expect(page.locator('[data-world-fps]')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true
    );
    await page.getByRole('button', { name: 'Close performance' }).click();
    for (const label of ['Follow my character', 'Zoom in', 'Zoom out']) {
      const bounds = await page.getByRole('button', { name: label, exact: true }).boundingBox();
      expect(bounds?.width).toBeGreaterThanOrEqual(44);
      expect(bounds?.height).toBeGreaterThanOrEqual(44);
      expect((bounds?.y ?? 10000) + (bounds?.height ?? 0)).toBeLessThanOrEqual(844);
    }
    await page.screenshot({ path: info.outputPath('world-mobile.png'), fullPage: true });
    await page.setViewportSize({ width: 320, height: 740 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true
    );
    await expect(page.getByRole('button', { name: 'Zoom in', exact: true })).toBeVisible();
  });
});

test('world: protected route preserves shell navigation and removes duplicate decoration', async ({
  page,
  authenticate,
}) => {
  await authenticate();
  await enableWorld(page);
  await page.goto('/en/dashboard/world');
  await expect(page.getByRole('heading', { name: 'LIA World' })).toBeVisible();
  await expect(page.locator('.world-admission')).toBeVisible();
  await expect(page.locator('canvas.world-canvas')).toHaveCount(0);
  await expect(page.getByTestId('app-cosmos')).toHaveCount(0);
  expect(new URL(page.url()).pathname).toBe('/en/dashboard/world');
});

test('world: accessible controls, context recovery and repeated ownership changes', async ({
  page,
  authenticate,
}, info) => {
  const user = await authenticate();
  await installInertWorldAdmission(page, user.id);
  await page.goto('/de/dashboard/world');
  await enterInertWorld(page);
  const canvas = page.locator('canvas.world-canvas');
  await expect(canvas).toBeVisible();
  const scan = await scanPage(page, info, 'world-german');
  expect(scan.blocking, scan.summary).toEqual([]);
  await canvas.dispatchEvent('contextlost');
  await expect(page.locator('.world-fallback[role="alert"]')).toBeVisible();
  await page.getByRole('button', { name: 'Erneut versuchen' }).click();
  await expect(canvas).toBeVisible();
  // A detached old scene must release its backing surface on SPA navigation.
  await page.goto('/en/dashboard/world');
  for (let i = 0; i < 3; i++) {
    await enterInertWorld(page);
    await expect(canvas).toBeVisible();
    const old = await canvas.elementHandle();
    await page.getByRole('link', { name: 'Help', exact: true }).first().click();
    await expect(page).toHaveURL(/dashboard\/faq$/, { timeout: 30_000 });
    await expect
      .poll(() =>
        old?.evaluate(element => (element instanceof HTMLCanvasElement ? element.width : null))
      )
      .toBe(1);
    await page.getByRole('link', { name: 'LIA World', exact: true }).first().click();
  }
  await enterInertWorld(page);
  await expect(canvas).toBeVisible();
});

test('world: real multi-touch pinch and CPU-throttled rendering evidence', async ({
  page,
  authenticate,
  browserName,
}, info) => {
  test.skip(browserName !== 'chromium', 'CDP touch and CPU emulation are Chromium-specific');
  await page.setViewportSize({ width: 390, height: 844 });
  const user = await authenticate();
  await installInertWorldAdmission(page, user.id);
  await page.goto('/en/dashboard/world');
  await enterInertWorld(page);
  const canvas = page.locator('canvas.world-canvas');
  await expect(canvas).toBeVisible();
  const client = await page.context().newCDPSession(page);
  await client.send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 2 });
  const initial = await page.locator('[data-world-zoom]').innerText();
  const before = await actorPosition(page);
  const touch = (x: number, id: number) => ({ x, y: 380, id, radiusX: 3, radiusY: 3 });
  await client.send('Input.dispatchTouchEvent', {
    type: 'touchStart',
    touchPoints: [touch(140, 1), touch(230, 2)],
  });
  await client.send('Input.dispatchTouchEvent', {
    type: 'touchMove',
    touchPoints: [touch(110, 1), touch(260, 2)],
  });
  await client.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await expect(page.locator('[data-world-zoom]')).not.toHaveText(initial);
  await expect.poll(() => actorPosition(page)).toEqual(before);
  await revealWorldControls(page);
  await page.getByRole('button', { name: 'How to explore', exact: true }).click();
  await page.getByRole('combobox', { name: 'Graphics quality' }).selectOption('low');
  await page.getByRole('button', { name: 'Explore', exact: true }).click();
  await page.getByRole('button', { name: 'Performance', exact: true }).click();
  await client.send('Emulation.setCPUThrottlingRate', { rate: 4 });
  try {
    await page.waitForTimeout(6500);
    await expect
      .poll(async () => Number(await page.locator('[data-world-fps]').innerText()))
      .toBeGreaterThan(0);
    await info.attach('world-throttled-performance', {
      contentType: 'application/json',
      body: JSON.stringify({
        profile: 'Headless Chromium in Docker, 4x CPU slowdown; not physical mobile hardware',
        viewport: page.viewportSize(),
        quality: 'low',
        fps: await page.locator('[data-world-fps]').innerText(),
        frameP95: await page.locator('[data-world-frame]').innerText(),
        renderP95: await page.locator('[data-world-render]').innerText(),
      }),
    });
    await page.screenshot({ path: info.outputPath('world-mobile-throttled.png') });
  } finally {
    await client.send('Emulation.setCPUThrottlingRate', { rate: 1 });
    await client.detach();
  }
});
