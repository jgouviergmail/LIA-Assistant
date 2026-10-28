/** Native admission, real safe JPEG composition and pixel privacy; no authority doubles. */
import { test, expect, type Page } from './fixtures';
import { stat } from 'node:fs/promises';
import { player, type Player } from './world-arcade-helpers';
import { revealWorldControls } from '../fixtures/world-admission';
import en from '../../locales/en/translation.json';
import AxeBuilder from '@axe-core/playwright';
import { WORLD } from '../../src/features/world/definition';
import { compileNavigation, findRoute } from '../../src/features/world/navigation';

async function openPhoto(person: Player) {
  await revealWorldControls(person.page);
  const tools = person.page.locator('.world-device-toggle');
  if ((await tools.isVisible()) && (await tools.getAttribute('aria-expanded')) === 'false')
    await tools.click();
  await person.page.getByRole('button', { name: en.world.photo.title, exact: true }).click();
  const dialog = person.page.getByRole('dialog', { name: en.world.photo.title, exact: true });
  await expect(dialog).toBeVisible();
  const image = dialog.getByRole('img', { name: en.world.photo.preview });
  await expect(image).toBeVisible();
  await image.evaluate(async node => {
    if (!(node instanceof HTMLImageElement)) throw new Error('Not an image');
    await node.decode();
  });
  await expect(
    dialog.getByRole('button', { name: en.world.photo.portrait, exact: true })
  ).not.toHaveAttribute('aria-disabled', 'true');
  return { dialog, image };
}
async function photoPixels(image: import('@playwright/test').Locator) {
  return image.evaluate(node => {
    if (!(node instanceof HTMLImageElement)) throw new Error('No photo');
    const canvas = document.createElement('canvas');
    canvas.width = node.naturalWidth;
    canvas.height = node.naturalHeight;
    const context = canvas.getContext('2d');
    if (!context) throw new Error('No context');
    context.drawImage(node, 0, 0);
    return canvas.toDataURL('image/png');
  });
}
async function crop(
  page: Page,
  pixels: string,
  rect: { x: number; y: number; width: number; height: number }
) {
  return page.evaluate(
    async ({ pixels, region }) => {
      const node = new Image();
      node.src = pixels;
      await node.decode();
      const canvas = document.createElement('canvas');
      canvas.width = region.width;
      canvas.height = region.height;
      const context = canvas.getContext('2d');
      if (!context) throw new Error('No context');
      context.drawImage(
        node,
        region.x,
        region.y,
        region.width,
        region.height,
        0,
        0,
        region.width,
        region.height
      );
      return Array.from(context.getImageData(0, 0, region.width, region.height).data);
    },
    { pixels, region: rect }
  );
}
async function download(page: Page, filename: string) {
  const pending = page.waitForEvent('download');
  await page.getByRole('link', { name: en.world.photo.download, exact: true }).click();
  const result = await pending;
  expect(result.suggestedFilename()).toBe('lia-world-photo.jpg');
  await result.saveAs(filename);
  expect((await stat(filename)).size).toBeLessThanOrEqual(2 * 1024 * 1024);
  expect(await result.failure()).toBeNull();
}
test('photo excludes a visible peer while retaining the same scenery and exports both formats', async ({
  browser,
  baseURL,
}, info) => {
  test.setTimeout(180000);
  if (!baseURL) throw new Error('Disposable proof URL required');
  const host = await player(browser, baseURL, 8, 'Photo Owner', 1280);
  const engine = await browser.browserType().launch({ headless: true });
  let peer: Player | null = null;
  try {
    // Keep the deliberately included companion beside the stationary owner;
    // a patrolling LIA must not cross the background region under comparison.
    await revealWorldControls(host.page);
    const follow = host.page.getByRole('button', { name: en.world.call_bip, exact: true });
    await follow.click();
    await expect(follow).toHaveAttribute('aria-pressed', 'true');
    await host.page.getByRole('button', { name: en.world.zoom_in, exact: true }).click();
    const selectedZoom =
      Number((await host.page.locator('[data-world-zoom]').innerText()).replace('%', '')) / 100;
    expect(selectedZoom).toBeGreaterThan(0.95);
    const settle = Date.now();
    await expect.poll(() => Date.now() - settle, { intervals: [200] }).toBeGreaterThan(5000);
    const first = await openPhoto(host);
    // Read the displayed safe photo while its URL is still owned. A detached
    // image whose Blob URL was revoked is not a portable pixel reference.
    const reference = await photoPixels(first.image);
    await info.attach('baseline-photo.png', {
      body: Buffer.from(reference.split(',')[1], 'base64'),
      contentType: 'image/png',
    });
    const size = await first.image.evaluate(node => {
      if (!(node instanceof HTMLImageElement)) throw new Error('No image');
      return { width: node.naturalWidth, height: node.naturalHeight };
    });
    expect(size).toEqual({ width: 1600, height: 900 });
    await host.page.keyboard.press('Escape');
    peer = await player(engine, baseURL, 7, 'Visible Secret Guest', 1280);
    const origin = host.view()?.you?.position;
    if (!origin) throw new Error('No owner position');
    // Route through reachable foreground, instead of timing arrow holds that
    // can correctly stop at a bench on a loaded engine.
    const navigation = compileNavigation(WORLD);
    const start = peer.view()?.you?.position;
    if (!start) throw new Error('No peer start');
    const target = [
      { x: 8, y: 2 },
      { x: 2, y: 8 },
      { x: 7, y: 1 },
      { x: 1, y: 7 },
    ]
      .map(offset => ({ x: origin.x + offset.x, y: origin.y + offset.y }))
      .find(candidate => findRoute(navigation, start, candidate).length > 0);
    if (!target) throw new Error('No reachable photo foreground');
    await revealWorldControls(peer.page);
    await peer.page.getByRole('button', { name: en.world.recenter, exact: true }).click();
    const recentered = Date.now();
    await expect.poll(() => Date.now() - recentered, { intervals: [100] }).toBeGreaterThan(700);
    const peerBounds = await peer.page.locator('canvas.world-canvas').boundingBox();
    if (!peerBounds) throw new Error('No peer scene');
    const click = {
      x:
        peerBounds.x + peerBounds.width / 2 + (target.x - start.x - target.y + start.y) * 32 * 0.95,
      y:
        peerBounds.y +
        peerBounds.height / 2 +
        ((target.x - start.x + target.y - start.y) * 16 + 28) * 0.95,
    };
    expect(
      await peer.page.evaluate(
        point =>
          document.elementFromPoint(point.x, point.y) ===
          document.querySelector('canvas.world-canvas'),
        click
      )
    ).toBe(true);
    await peer.page.mouse.click(click.x, click.y);
    await expect
      .poll(
        () => {
          const point = peer?.view()?.you?.position;
          return point ? Math.hypot(point.x - target.x, point.y - target.y) : Infinity;
        },
        { timeout: 30000 }
      )
      .toBeLessThan(0.35);
    const moved = peer.view()?.you?.position;
    if (!moved) throw new Error('No confirmed peer position');
    expect(Math.abs((moved.x - origin.x - moved.y + origin.y) * 32)).toBeGreaterThan(140);
    await expect
      .poll(() => host.view()?.actors.some(actor => actor.alias === 'Visible Secret Guest'))
      .toBe(true);
    await expect.poll(() => peer?.view()?.you?.walking).toBe(false);
    const point = peer.view()?.you?.position;
    if (!point) throw new Error('No peer position');
    const bounds = await host.page.locator('canvas.world-canvas').boundingBox();
    if (!bounds) throw new Error('No scene bounds');
    const scale = Math.max(size.width / bounds.width, size.height / bounds.height) * selectedZoom;
    const x = size.width / 2 + (point.x - origin.x - point.y + origin.y) * 32 * scale;
    const y = size.height / 2 + ((point.x - origin.x + point.y - origin.y) * 16 + 28) * scale;
    const region = {
      x: Math.round(x - 20 * scale),
      y: Math.round(y - 62 * scale),
      width: Math.round(40 * scale),
      height: Math.round(48 * scale),
    };
    expect(region.x).toBeGreaterThan(0);
    expect(region.y).toBeGreaterThan(0);
    expect(region.x + region.width).toBeLessThan(size.width);
    expect(region.y + region.height).toBeLessThan(size.height);
    await host.page.screenshot({ path: info.outputPath('live-with-visible-peer.png') });
    const second = await openPhoto(host);
    const current = await photoPixels(second.image);
    const before = await crop(host.page, reference, region),
      after = await crop(host.page, current, region);
    const difference =
      before.reduce((sum, value, index) => sum + Math.abs(value - after[index]), 0) / before.length;
    await info.attach('current-photo.png', {
      body: Buffer.from(current.split(',')[1], 'base64'),
      contentType: 'image/png',
    });
    await info.attach('pixel-region.json', {
      body: JSON.stringify({ region, difference, origin, point, bounds }),
      contentType: 'application/json',
    });
    expect(difference).toBeLessThan(6);
    await download(host.page, info.outputPath('private-landscape.jpg'));
    await second.dialog.getByRole('button', { name: en.world.photo.portrait, exact: true }).click();
    await expect(second.image).toHaveAttribute('height', '1600');
    await second.image.evaluate(async node => {
      if (!(node instanceof HTMLImageElement)) throw new Error('No image');
      await node.decode();
    });
    await expect(
      second.dialog.getByRole('button', { name: en.world.photo.landscape, exact: true })
    ).not.toHaveAttribute('aria-disabled', 'true');
    await download(host.page, info.outputPath('private-portrait.jpg'));
    await second.dialog.screenshot({ path: info.outputPath('portrait-preview.png') });
    await host.page.keyboard.press('Escape');
    expect(host.paid).toEqual([]);
    expect(host.errors).toEqual([]);
    await info.attach('photo-privacy-pixel-proof', {
      body: JSON.stringify({
        region,
        difference,
        peerVisibleInNativeView: true,
        sourceOwner: origin,
        peerPosition: point,
      }),
      contentType: 'application/json',
    });
  } finally {
    await host.context.close();
    await peer?.context.close();
    await engine.close();
  }
});

test('photo remains accessible at 320px and after rotation, with repeated close and reopen', async ({
  browser,
  baseURL,
}, info) => {
  if (!baseURL) throw new Error('Disposable proof URL required');
  const person = await player(browser, baseURL, 8, 'Photo Owner', 390);
  try {
    for (const size of [
      { width: 320, height: 740 },
      { width: 390, height: 844 },
      { width: 844, height: 390 },
    ]) {
      await person.page.setViewportSize(size);
      const { dialog, image } = await openPhoto(person);
      if (size.width > size.height) {
        await dialog.getByRole('button', { name: en.world.photo.portrait, exact: true }).click();
        await expect(image).toHaveAttribute('height', '1600');
      }
      const bounds = await dialog.boundingBox();
      if (!bounds) throw new Error('No dialog');
      expect(bounds.x).toBeGreaterThanOrEqual(0);
      expect(bounds.x + bounds.width).toBeLessThanOrEqual(size.width);
      expect(bounds.y).toBeGreaterThanOrEqual(0);
      expect(bounds.y + bounds.height).toBeLessThanOrEqual(size.height);
      const scan = await new AxeBuilder({ page: person.page })
        .include('[data-world-native-panel]')
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
        .analyze();
      expect(scan.violations).toEqual([]);
      await dialog.screenshot({ path: info.outputPath(`photo-${size.width}.png`) });
      expect(await image.evaluate(node => node instanceof HTMLImageElement && node.complete)).toBe(
        true
      );
      await person.page.keyboard.press('Escape');
      await expect(dialog).toHaveCount(0);
      await expect
        .poll(() => person.page.evaluate(() => document.activeElement?.getAttribute('aria-label')))
        .toBe(en.world.photo.title);
    }
    expect(person.errors).toEqual([]);
    expect(person.paid).toEqual([]);
  } finally {
    await person.context.close();
  }
});
