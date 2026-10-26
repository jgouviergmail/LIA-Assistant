import { worldProofUrl } from './world-route';
import { enterWorld } from '../fixtures/world-admission';
/** Native admission and rendering; no socket/API mocks or provider calls. */
import { test, expect } from './fixtures';
import fr from '../../locales/fr/translation.json';
import { installOfflineFonts } from '../fixtures/offline-fonts';

test('mobile HUD unfolds, joystick releases and private panels retain the same scene cadence', async ({
  browser,
  baseURL,
}, info) => {
  // Native config requires an explicit isolated origin; proof-session success
  // below fences the fixture from ordinary application accounts.
  if (!baseURL) throw new Error('Explicit disposable QA required');
  const context = await browser.newContext({
    baseURL,
    viewport: { width: 390, height: 844 },
    hasTouch: true,
    reducedMotion: 'no-preference',
    serviceWorkers: 'block',
  });
  const page = await context.newPage();
  const errors: string[] = [];
  const positions: { x: number; y: number }[] = [];
  let movingFrames = 0;
  page.on('websocket', socket => {
    if (!socket.url().endsWith('/world/ws')) return;
    socket.on('framereceived', event => {
      const value: unknown = JSON.parse(String(event.payload));
      if (!value || typeof value !== 'object' || !('you' in value)) return;
      const you = value.you;
      if (!you || typeof you !== 'object' || !('position' in you)) return;
      const point = you.position;
      if (
        point &&
        typeof point === 'object' &&
        'x' in point &&
        'y' in point &&
        typeof point.x === 'number' &&
        typeof point.y === 'number'
      )
        positions.push({ x: point.x, y: point.y });
    });
    socket.on('framesent', event => {
      const value: unknown = JSON.parse(String(event.payload));
      if (
        value &&
        typeof value === 'object' &&
        'type' in value &&
        value.type === 'move' &&
        'dx' in value &&
        'dy' in value &&
        (value.dx !== 0 || value.dy !== 0)
      )
        movingFrames++;
    });
  });
  page.on('pageerror', error => errors.push(error.message));
  try {
    expect(
      (
        await context.request.post('/api/v1/world-proof/session', {
          headers: { Origin: new URL(baseURL).origin },
          data: { index: 1 },
        })
      ).status()
    ).toBe(200);
    await installOfflineFonts(page);
    await page.goto(worldProofUrl(baseURL, 'fr').href);
    await enterWorld(page);
    const scene = page.locator('.world-prototype');
    await expect(scene).toHaveAttribute('data-world-status', 'shared');
    await expect(scene).toHaveAttribute('data-hud-expanded', 'false');
    const toggle = page.getByRole('button', { name: fr.world.controls, exact: true });
    const stick = page.locator('.world-joystick');
    await expect(stick).toBeVisible();
    await expect(page.locator('.world-top')).toBeHidden();
    await expect(page.locator('[data-world-conversations]')).toBeVisible();
    await page.screenshot({ path: info.outputPath('mobile-folded.png') });
    const box = await stick.boundingBox();
    if (!box) throw new Error('Missing joystick');
    const before = positions.at(-1);
    if (!before) throw new Error('Missing authoritative position');
    await page.mouse.move(box.x + 44, box.y + 44);
    await page.mouse.down();
    await page.mouse.move(box.x + 74, box.y + 44);
    await expect.poll(() => movingFrames).toBeGreaterThan(0);
    await expect
      .poll(() => {
        const point = positions.at(-1);
        return point ? Math.hypot(point.x - before.x, point.y - before.y) : 0;
      })
      .toBeGreaterThan(0.02);
    await page.mouse.up();
    await expect(stick.locator('.world-joystick-thumb')).toHaveCSS(
      'transform',
      'matrix(1, 0, 0, 1, 0, 0)'
    );
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await expect(page.locator('.world-top')).toBeVisible();
    await expect(stick).toBeHidden();
    await page.getByRole('button', { name: fr.world.help, exact: true }).click();
    const dialog = page.getByRole('dialog');
    const visibility = dialog.getByLabel(fr.world.joystick.label, { exact: true });
    await visibility.selectOption('hide');
    await dialog.getByRole('button', { name: fr.world.play, exact: true }).click();
    await toggle.click();
    await expect(stick).toHaveCount(0);
    await toggle.click();
    await page.getByRole('button', { name: fr.world.metrics, exact: true }).click();
    await page.waitForTimeout(6500);
    console.info('before-panel-metrics', await page.locator('.world-metrics').innerText());
    const baselineFps = Number(
      (await page.locator('[data-world-fps]').textContent())?.replace(',', '.')
    );
    expect(baselineFps).toBeGreaterThan(0);
    await page.getByRole('button', { name: fr.world.messages.action, exact: true }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    // Let the bounded frame meter replace its pre-panel samples.
    await page.waitForTimeout(6500);
    console.info('panel-metrics', await page.locator('.world-metrics').innerText());
    await expect
      .poll(
        async () =>
          Number((await page.locator('[data-world-fps]').textContent())?.replace(',', '.')),
        { timeout: 10000 }
      )
      .toBeGreaterThanOrEqual(baselineFps * 0.8);
    await page.screenshot({ path: info.outputPath('mobile-panel.png') });
    await page.keyboard.press('Escape');
    await page.setViewportSize({ width: 844, height: 390 });
    // A resize clears the drawing buffer; wait for actual world pixels before the visual evidence.
    await expect
      .poll(() =>
        page.locator('.world-canvas').evaluate(canvas => {
          if (!(canvas instanceof HTMLCanvasElement)) return 0;
          const c = canvas.getContext('2d');
          if (!c || !canvas.width || !canvas.height) return 0;
          // Do not mistake the old portrait buffer for the newly painted landscape buffer.
          if (
            canvas.width !== Math.round(canvas.clientWidth) ||
            canvas.height !== Math.round(canvas.clientHeight)
          )
            return 0;
          const colors = new Set<string>();
          for (let y = 1; y <= 5; y++)
            for (let x = 1; x <= 5; x++)
              colors.add(
                String(
                  c.getImageData(
                    Math.floor((canvas.width * x) / 6),
                    Math.floor((canvas.height * y) / 6),
                    1,
                    1
                  ).data
                )
              );
          return colors.size;
        })
      )
      .toBeGreaterThan(4);

    await page.evaluate(
      () =>
        new Promise<void>(resolve =>
          requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
        )
    );
    await page.screenshot({ path: info.outputPath('landscape-expanded.png') });
    expect(errors).toEqual([]);
  } finally {
    await page.keyboard.press('Escape');
    const toggle = page.locator('.world-hud-toggle');
    if ((await toggle.isVisible()) && (await toggle.getAttribute('aria-expanded')) === 'false')
      await toggle.click();
    const leave = page.getByRole('button', { name: fr.world.session.leave, exact: true });
    if (await leave.isVisible()) await leave.click();
    await context.close();
  }
});
