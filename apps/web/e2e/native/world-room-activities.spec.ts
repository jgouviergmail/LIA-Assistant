import { openNativeWorld } from '../fixtures/world-admission';
/** Real authored object pixels, native owner panels and server-confirmed activity seats. */
import { test, expect, type Page } from './fixtures';
import en from '../../locales/en/translation.json';
import { WORLD } from '../../src/features/world/definition';
import type { WorldView } from '../../src/features/world/protocol';
import { frameWorldProp } from '../fixtures/world-scene-navigation';
import { installOfflineFonts } from '../fixtures/offline-fonts';
import { worldProofUrl } from './world-route';
async function pointAt(page: Page, key: string) {
  const prop = WORLD.props.find(p => p.key === key);
  if (!prop) throw new Error('Missing authored activity ' + key);
  return frameWorldProp(page, prop, id => en.world.zones[id as keyof typeof en.world.zones]);
}
test('room activities select exact gallery tabs, confirmed seats and localized unsent drafts inside the world', async ({
  browser,
  baseURL,
}, info) => {
  test.setTimeout(180000);
  if (!baseURL) throw new Error('Explicit isolated host required');
  const context = await browser.newContext({
    baseURL,
    viewport: { width: 1280, height: 800 },
    serviceWorkers: 'block',
  });
  const page = await context.newPage();
  const errors: string[] = [],
    paid: string[] = [];
  let latest: WorldView | null = null;
  const view = () => latest;
  page.on('pageerror', e => errors.push(e.message));
  page.on('websocket', socket => {
    if (socket.url().endsWith('/world/ws'))
      socket.on('framereceived', ({ payload }) => {
        const frame = JSON.parse(String(payload)) as WorldView;
        if (frame.type === 'snapshot') latest = frame;
      });
  });
  page.on('request', r => {
    if (r.method() === 'POST' && /agents\/chat|world\/messages\/(send|translate)/.test(r.url()))
      paid.push(r.url());
  });
  try {
    const login = await context.request.post('/api/v1/world-proof/session', {
      headers: { Origin: new URL(baseURL).origin },
      data: { index: 2 },
    });
    expect(login.status()).toBe(200);
    const flags = (await (await context.request.get('/api/v1/config')).json()) as {
      features: { bookmarks_enabled?: boolean };
    };
    await installOfflineFonts(page);
    const url = worldProofUrl(baseURL, 'en');
    url.searchParams.set('tab', 'documents');
    await openNativeWorld(page, 'Room activities visitor', url);
    if (await page.locator('input[name="world-presence-consent"]').isVisible())
      await page.locator('input[name="world-presence-consent"]').check();
    await page.getByRole('button', { name: en.world.session.enter, exact: true }).click();
    await expect.poll(() => latest?.status).toBe('active');
    const takeover = page.getByRole('button', { name: en.world.session.takeover, exact: true });
    if (await takeover.isVisible()) await takeover.click();
    const originalUrl = page.url();
    for (const [index, tab] of (
      ['images', 'documents', 'screenshots', 'bookmarks'] as const
    ).entries()) {
      if (tab === 'bookmarks' && !flags.features.bookmarks_enabled) continue;
      const point = await pointAt(page, 'gallery-' + index);
      await page.mouse.move(point.x, point.y);
      await expect(page.getByRole('tooltip')).toContainText(
        en.settings.generated_assets.family[tab]
      );
      await page.mouse.click(point.x, point.y);
      await expect(
        page.getByRole('tab', { name: en.settings.generated_assets.family[tab], exact: true })
      ).toHaveAttribute('aria-selected', 'true', { timeout: 30000 });
      expect(page.url()).toBe(originalUrl);
      await page.screenshot({ path: info.outputPath('gallery-' + tab + '.png') });
      await page.keyboard.press('Escape');
    }
    const seat = await pointAt(page, 'gallery-seat-0');
    await page.mouse.move(seat.x, seat.y);
    await expect(page.getByRole('tooltip')).toContainText(en.world.poses.sit);
    await page.mouse.click(seat.x, seat.y);
    await expect(
      page.getByRole('tab', { name: en.settings.generated_assets.family.images, exact: true })
    ).toHaveAttribute('aria-selected', 'true', { timeout: 30000 });
    expect(view()?.you?.pose).toBe('gallery-seat-0:0');
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(
      page.getByRole('tab', { name: en.settings.generated_assets.family.images, exact: true })
    ).toBeInViewport();
    await page.screenshot({ path: info.outputPath('gallery-seat-mobile.png') });
    await page.keyboard.press('Escape');
    await page.setViewportSize({ width: 1280, height: 800 });
    for (const [key, draft] of [
      ['generate-image', en.world.activities.image_draft],
      ['phone', en.world.activities.call_draft],
    ] as const) {
      const point = await pointAt(page, key);
      await page.mouse.click(point.x, point.y);
      await expect(page.getByRole('dialog').locator('textarea')).toHaveValue(draft, {
        timeout: 30000,
      });
      expect(page.url()).toBe(originalUrl);
      expect(paid).toEqual([]);
      await page.keyboard.press('Escape');
    }
    expect(errors).toEqual([]);
    expect(paid).toEqual([]);
  } finally {
    await page.keyboard.press('Escape');
    const leave = page.getByRole('button', { name: en.world.session.leave, exact: true });
    if (await leave.count()) await leave.last().click();
    await context.close();
  }
});
