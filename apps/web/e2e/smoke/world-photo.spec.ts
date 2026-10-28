/**
 * Hermetic photo journey: the preview is composed inside the page, downloads as
 * the generic JPEG, never leaves in a request, and reaches the system share
 * sheet only on an explicit press. Pixel privacy (a visible peer excluded) is
 * proven against the native authority in `native/world-photo.spec.ts`.
 */
import { readFile } from 'node:fs/promises';
import { test, expect } from '../fixtures';
import type { Page } from '@playwright/test';
import { installInertWorldAdmission } from '../fixtures/world-session';
import { enterWorld, revealWorldControls } from '../fixtures/world-admission';
import { scanPage } from '../a11y/scan';
import en from '../../locales/en/translation.json';

interface SharedFile {
  name: string;
  type: string;
  size: number;
}
declare global {
  interface Window {
    worldShareProbe: { files: SharedFile[] };
  }
}
interface SentBody {
  method: string;
  path: string;
  type: string;
  bytes: number;
  jpeg: boolean;
}
const JPEG_START = Buffer.from([0xff, 0xd8, 0xff]);

/** A system share sheet that only records what an explicit press handed it. */
async function installShareProbe(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const probe: { files: { name: string; type: string; size: number }[] } = { files: [] };
    window.worldShareProbe = probe;
    Object.defineProperty(navigator, 'canShare', {
      configurable: true,
      value: (data?: ShareData) => Array.isArray(data?.files) && data.files.length > 0,
    });
    Object.defineProperty(navigator, 'share', {
      configurable: true,
      value: async (data?: ShareData) => {
        for (const file of data?.files ?? [])
          probe.files.push({ name: file.name, type: file.type, size: file.size });
      },
    });
  });
}
/** Every request body the page sends, read where it leaves: nothing may carry the photo. */
function observeBodies(page: Page): SentBody[] {
  const sent: SentBody[] = [];
  page.on('request', request => {
    const body = request.postDataBuffer();
    if (!body?.length) return;
    sent.push({
      method: request.method(),
      path: new URL(request.url()).pathname,
      type: request.headers()['content-type'] ?? '',
      bytes: body.length,
      jpeg: body.includes(JPEG_START),
    });
  });
  return sent;
}
async function openPhoto(page: Page) {
  await revealWorldControls(page);
  const tools = page.locator('.world-device-toggle');
  if ((await tools.isVisible()) && (await tools.getAttribute('aria-expanded')) === 'false')
    await tools.click();
  await page.getByRole('button', { name: en.world.photo.title, exact: true }).click();
  const dialog = page.getByRole('dialog', { name: en.world.photo.title, exact: true });
  await expect(dialog).toBeVisible();
  const image = dialog.getByRole('img', { name: en.world.photo.preview });
  await expect(image).toBeVisible();
  await image.evaluate(async node => {
    if (!(node instanceof HTMLImageElement)) throw new Error('The preview is not an image');
    await node.decode();
  });
  return { dialog, image };
}

for (const [device, viewport] of [
  ['desktop', { width: 1280, height: 900 }],
  ['phone', { width: 390, height: 844 }],
] as const)
  test(`photo previews locally, downloads the generic JPEG and shares only on request (${device})`, async ({
    page,
    authenticate,
  }, info) => {
    await page.setViewportSize(viewport);
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await installShareProbe(page);
    const user = await authenticate();
    await installInertWorldAdmission(page, user.id);
    await page.goto('/en/dashboard/world');
    await enterWorld(page);
    await expect(page.locator('.world-prototype')).toHaveAttribute('data-world-status', 'shared');

    const sent = observeBodies(page);
    const { dialog, image } = await openPhoto(page);
    expect(await image.getAttribute('src')).toMatch(/^blob:/);
    const share = dialog.getByRole('button', { name: en.world.photo.share, exact: true });
    await expect(share).toBeVisible();
    // Opening composes a preview; it never offers the photo to anyone.
    expect(await page.evaluate(() => window.worldShareProbe.files)).toEqual([]);
    const scan = await scanPage(page, info, `world-photo-${device}`, '[data-world-native-panel]');
    expect(scan.blocking, scan.summary).toEqual([]);

    const link = dialog.getByRole('link', { name: en.world.photo.download, exact: true });
    await expect(link).toHaveAttribute('href', /^blob:/);
    const pending = page.waitForEvent('download');
    await link.click();
    const download = await pending;
    expect(download.suggestedFilename()).toBe('lia-world-photo.jpg');
    const saved = info.outputPath(`world-photo-${device}.jpg`);
    await download.saveAs(saved);
    expect(await download.failure()).toBeNull();
    const bytes = await readFile(saved);
    expect([...bytes.subarray(0, 3)]).toEqual([...JPEG_START]);
    expect([...bytes.subarray(-2)]).toEqual([0xff, 0xd9]);
    expect(await page.evaluate(() => window.worldShareProbe.files)).toEqual([]);

    await share.click();
    await expect(
      dialog.getByRole('status').filter({ hasText: en.world.photo.offered })
    ).toBeVisible();
    expect(await page.evaluate(() => window.worldShareProbe.files)).toEqual([
      { name: 'lia-world-photo.jpg', type: 'image/jpeg', size: bytes.length },
    ]);
    await dialog.screenshot({ path: info.outputPath(`world-photo-${device}.png`) });
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect
      .poll(() => page.evaluate(() => document.activeElement?.getAttribute('aria-label')))
      .toBe(en.world.photo.title);

    // The whole journey sent no image, no multipart form and no file bytes.
    expect(
      sent.filter(body => body.jpeg || /^(image|multipart)\//i.test(body.type)),
      JSON.stringify(sent)
    ).toEqual([]);
    expect(errors).toEqual([]);
  });
