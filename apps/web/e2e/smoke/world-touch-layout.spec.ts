/** Touch capability survives rotation; native HUD actions remain reachable. */
import { test, expect } from '../fixtures';
import { installInertWorldAdmission } from '../fixtures/world-session';
import { scanPage } from '../a11y/scan';
import { appConfig } from '../fixtures/dashboard-shell';
import { cssPixels } from '../native/layout';

test.use({ viewport: { width: 390, height: 844 }, hasTouch: true });

for (const peersEnabled of [false, true]) {
  test(`world: touch navigation survives rotation (${peersEnabled ? 'with' : 'without'} peers)`, async ({
    page,
    authenticate,
    mockApi,
  }, info) => {
    const errors: string[] = [];
    page.on('console', message => {
      if (message.type() === 'error') {
        errors.push(message.text());
        console.info('World layout browser error: ' + message.text().slice(0, 300));
      }
    });
    page.on('response', response => {
      if (response.status() >= 400)
        console.info('World layout HTTP', response.status(), new URL(response.url()).pathname);
    });
    const user = await authenticate();
    await installInertWorldAdmission(page, user.id);
    await mockApi([
      {
        url: '**/api/v1/config',
        json: {
          ...appConfig,
          features: {
            ...appConfig.features,
            world_enabled: true,
            peers_enabled: peersEnabled,
            radio_enabled: true,
          },
        },
      },
    ]);
    const now = Date.now() / 1000;
    await mockApi([
      {
        url: '**/api/v1/world/messages/read',
        json: {
          server_time: now,
          ttl_seconds: 1800,
          truncated: false,
          messages: Array.from({ length: 50 }, (_, index) => ({
            id: `5010c2c2-4bd0-4d21-9c08-${String(index).padStart(12, '0')}`,
            sender_id: '5010c2c2-4bd0-4d21-9c08-b4502db25d72',
            recipient_id: user.id,
            sender_alias: 'Peer',
            recipient_alias: 'Explorer',
            outgoing: false,
            original: 'Hello',
            text: 'Hello',
            language: 'en',
            status: 'original',
            created_at: now,
            expires_at: now + 1800,
            receipt: null,
          })),
        },
      },
    ]);
    await page.goto('/en/dashboard/world');
    await page.locator('.world-admission input[type="checkbox"]').check();
    await page.locator('.world-admission button[type="submit"]').click();
    const scene = page.locator('.world-prototype');
    // Phone, weather, independent world sound, radio and display mode.
    // Voice remains available from the application menu.
    await expect(page.locator('.world-device-controls button')).toHaveCount(5);
    await expect(scene).toBeVisible();
    const stick = page.locator('.world-joystick');
    const discussion = page.getByRole('button', { name: 'Chat with people', exact: true });
    await expect(discussion).toHaveAccessibleDescription('Unread messages: 50');
    const toggle = page.getByRole('button', { name: 'World controls', exact: true });
    for (const viewport of [
      { width: 390, height: 844 },
      { width: 844, height: 390 },
      { width: 568, height: 320 },
      { width: 320, height: 568 },
      { width: 320, height: 568, fontSize: 20 },
      { width: 768, height: 1024 },
      { width: 1024, height: 768 },
      { width: 1280, height: 800, fontSize: 20 },
      { width: 568, height: 320, fontSize: 20 },
    ]) {
      await page.setViewportSize(viewport);
      await page.evaluate(
        size => {
          document.documentElement.style.fontSize = size ? `${size}px` : '';
        },
        'fontSize' in viewport ? viewport.fontSize : undefined
      );
      const compact =
        viewport.width < 768 || (viewport.height <= 520 && viewport.width > viewport.height);
      if (compact && (await toggle.getAttribute('aria-expanded')) === 'true') await toggle.click();
      await expect(stick).toBeVisible();
      await scene.scrollIntoViewIfNeeded();
      const bounds = await scene.boundingBox();
      if (!bounds) throw new Error('Missing world scene');
      if (compact) {
        await expect(page.locator('.world-top')).toBeHidden();
        const dock = await page.locator('.world-session-strip').boundingBox();
        if (!dock) throw new Error('Missing compact action dock');
        expect(dock.width * dock.height).toBeLessThanOrEqual(bounds.width * bounds.height * 0.08);
      }
      // Visible folded controls must all have native touch targets and real hit tests.
      const controls = page
        .locator('.world-joystick, .world-hud-toggle, [data-world-conversations]')
        .filter({ visible: true });
      for (const button of await controls.all()) {
        // Trial hit tests can scroll the document. Read both rectangles in
        // one layout snapshot rather than compare against a previous scroll.
        const geometry = await button.evaluate(element => {
          const scene = element.ownerDocument.querySelector('.world-prototype');
          if (!scene) throw new Error('Missing current world scene');
          const box = element.getBoundingClientRect();
          const bounds = scene.getBoundingClientRect();
          return {
            box: { x: box.x, y: box.y, width: box.width, height: box.height },
            bounds: { x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height },
          };
        });
        const { box, bounds: currentBounds } = geometry;
        expect(cssPixels(box.width)).toBeGreaterThanOrEqual(44);
        expect(cssPixels(box.height)).toBeGreaterThanOrEqual(44);
        expect(box.x).toBeGreaterThanOrEqual(currentBounds.x);
        expect(box.y).toBeGreaterThanOrEqual(currentBounds.y);
        expect(box.x + box.width).toBeLessThanOrEqual(currentBounds.x + currentBounds.width + 1);
        expect(box.y + box.height).toBeLessThanOrEqual(currentBounds.y + currentBounds.height + 1);
        await button.click({ trial: true });
      }
      if (compact) {
        await toggle.click();
        await expect(page.locator('.world-top')).toBeVisible();
        await expect(stick).toBeHidden();
      }
      const toolsToggle = page.locator('.world-device-toggle');
      if (viewport.height <= 520 && viewport.width > viewport.height) {
        await toolsToggle.scrollIntoViewIfNeeded();
        await toolsToggle.click();
        await expect(page.locator('.world-device-shell')).toHaveAttribute('data-expanded', 'true');
        await page.keyboard.press('Escape');
      } else {
        await page.locator('.world-device-controls').scrollIntoViewIfNeeded();
        await expect(page.locator('.world-device-controls')).toBeVisible();
      }
      await discussion.click({ trial: true });
      if (compact) await toggle.click();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true
      );
      await page.screenshot({
        path: info.outputPath(
          `touch-${viewport.width}${'fontSize' in viewport ? '-enlarged' : ''}.png`
        ),
      });
    }
    // Enlarged app text must not push the native actions out of the play area.
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => {
      document.documentElement.style.fontSize = '20px';
    });
    await toggle.click();
    await page.getByRole('button', { name: 'Leave the world', exact: true }).click({ trial: true });
    await toggle.click();
    const before = Number(await page.locator('.world-minimap circle').last().getAttribute('cx'));
    await stick.hover();
    await page.mouse.down();
    const held = await stick.boundingBox();
    expect(cssPixels(held?.width), 'Held walking target stays reachable').toBeGreaterThanOrEqual(
      44
    );
    expect(cssPixels(held?.height)).toBeGreaterThanOrEqual(44);
    if (!held) throw new Error('Missing joystick');
    await page.mouse.move(held.x + held.width / 2 + 30, held.y + held.height / 2);
    await page.waitForTimeout(600);
    await page.mouse.up();
    await expect
      .poll(async () =>
        Number(await page.locator('.world-minimap circle').last().getAttribute('cx'))
      )
      .toBeGreaterThan(before + 0.3);
    const scan = await scanPage(page, info, 'world-touch-enlarged');
    expect(scan.blocking, scan.summary).toEqual([]);
    expect(errors).toEqual([]);
  });
}
