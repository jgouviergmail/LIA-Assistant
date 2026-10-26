import { createWorldDevice, closeWorldDevices } from '../fixtures/world-device';
import { worldProofUrl } from './world-route';
/** Real SQL, authenticated preference routes and authoritative actor projections. */
import { test, expect } from './fixtures';
import fr from '../../locales/fr/translation.json';
import { installOfflineFonts } from '../fixtures/offline-fonts';
import { enterWorld } from '../fixtures/world-admission';
import { frameWorldProp } from '../fixtures/world-scene-navigation';
import { WORLD } from '../../src/features/world/definition';

test('native appearance persists, broadcasts only its public style and edits through the studio mirror', async ({
  browser,
  baseURL,
}, info) => {
  test.setTimeout(150000);
  // Native config requires an explicit isolated origin; proof-session success
  // below fences the fixture from ordinary application accounts.
  if (!baseURL) throw new Error('Explicit disposable QA required');
  const context = await browser.newContext({ baseURL, viewport: { width: 1280, height: 850 } });
  const peerDevice = await createWorldDevice(browser, { baseURL });
  const peer = peerDevice.context;
  const page = await context.newPage();
  const other = await peer.newPage();
  const frames: unknown[] = [],
    errors: string[] = [];
  page.on('pageerror', e => errors.push(e.message));
  other.on('websocket', socket => {
    if (socket.url().endsWith('/world/ws'))
      socket.on('framereceived', e => frames.push(JSON.parse(String(e.payload))));
  });
  try {
    for (const [ctx, index] of [
      [context, 7],
      [peer, 8],
    ] as const) {
      const session = await ctx.request.post('/api/v1/world-proof/session', {
        headers: { Origin: new URL(baseURL).origin },
        data: { index },
      });
      expect(session.status()).toBe(200);
    }
    const me = await (await context.request.get('/api/v1/auth/me')).json();
    const before = await (await context.request.get('/api/v1/world/avatar')).json();
    expect(before.public_name).toBe(me.full_name.slice(0, 24));
    await installOfflineFonts(page);
    await installOfflineFonts(other);
    await page.goto(worldProofUrl(baseURL, 'fr').href);
    await expect(page.locator('[data-world-public-name]')).toHaveText(me.full_name.slice(0, 24));
    expect(await page.locator('input[name="world-alias"]').count()).toBe(0);
    // This also exercises repeat entry: if already configured, open the same explicit editor.
    const change = page.getByRole('button', { name: fr.world.avatar.change, exact: true });
    if (await change.isVisible()) await change.click();
    await page
      .getByRole('combobox', { name: fr.world.avatar.hair, exact: true })
      .selectOption('mohawk');
    await page.getByRole('radio', { name: fr.world.avatar.colors.violet, exact: true }).check();
    await page.screenshot({ path: info.outputPath('appearance-desktop.png') });
    await page.setViewportSize({ width: 320, height: 740 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true
    );
    await page.screenshot({ path: info.outputPath('appearance-mobile.png') });
    await enterWorld(page);
    await expect(page.locator('.world-prototype')).toHaveAttribute('data-world-status', 'shared');
    const saved = await (await context.request.get('/api/v1/world/avatar')).json();
    expect(saved.preferences.appearance.hair).toBe('mohawk');
    expect(saved.preferences.appearance.hair_color).toBe('violet');
    expect(saved.preferences.revision).toBe(before.preferences.revision + 1);
    await other.goto(worldProofUrl(baseURL, 'en').href);
    await enterWorld(other);
    await expect(other.locator('.world-prototype')).toHaveAttribute('data-world-status', 'shared');
    await expect
      .poll(() => frames.some(value => JSON.stringify(value).includes('"hair":"mohawk"')))
      .toBe(true);
    expect(JSON.stringify(frames)).not.toMatch(
      /world_avatar_preferences|appearance_revision|owner_id|email/
    );
    await page.setViewportSize({ width: 1280, height: 850 });
    const mirror = WORLD.props.find(p => p.activity === 'appearance');
    if (!mirror) throw new Error('Missing authored studio mirror');
    const point = await frameWorldProp(page, mirror, id => {
      const key = id as keyof typeof fr.world.zones;
      return fr.world.zones[key];
    });
    await page.mouse.click(point.x, point.y);
    const editor = page.locator('[data-world-avatar-editor]');
    await expect(editor).toBeVisible({ timeout: 90000 });
    await expect(
      editor.getByRole('combobox', { name: fr.world.avatar.hair, exact: true })
    ).toHaveValue('mohawk');
    await editor
      .getByRole('combobox', { name: fr.world.avatar.hair, exact: true })
      .selectOption('long');
    await editor.getByRole('tab', { name: fr.world.avatar.tabs.outfit, exact: true }).click();
    await editor
      .getByRole('combobox', { name: fr.world.avatar.outfit, exact: true })
      .selectOption('suit');
    await editor.getByRole('button', { name: fr.world.home.save, exact: true }).click();
    await expect(editor).toHaveCount(0);
    await expect
      .poll(
        async () =>
          (await (await context.request.get('/api/v1/world/avatar')).json()).preferences.appearance
            .hair
      )
      .toBe('long');
    await page.screenshot({ path: info.outputPath('mirror-studio.png') });
    expect(errors).toEqual([]);
  } finally {
    try {
      for (const p of [page, other]) {
        if (p.isClosed()) continue;
        await p.keyboard.press('Escape');
        const leave = p.locator('.world-session-strip button').last();
        if (await leave.isVisible()) await leave.click();
      }
    } finally {
      await closeWorldDevices([{ context, close: () => context.close() }, peerDevice]);
    }
  }
});
