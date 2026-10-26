/** Real scene picking and authoritative seating; no teleport or pose mock. */
import { test, expect, type Page } from './fixtures';
import { frameWorldProp } from '../fixtures/world-scene-navigation';
import en from '../../locales/en/translation.json';
import { WORLD } from '../../src/features/world/definition';
import type { WorldView } from '../../src/features/world/protocol';
import { installOfflineFonts } from '../fixtures/offline-fonts';
import { worldProofUrl } from './world-route';
import { openNativeWorld, enterWorld } from '../fixtures/world-admission';
import { worldTransportFault } from './transport';
import { enterNativeTransportPeer } from '../fixtures/world-native-peer';

function observe(page: Page) {
  let view: WorldView | null = null;
  page.on('websocket', socket => {
    if (!socket.url().endsWith('/world/ws')) return;
    socket.on('framereceived', ({ payload }) => {
      const frame = JSON.parse(String(payload)) as WorldView;
      if (frame.type === 'snapshot') view = frame;
    });
  });
  return () => view;
}
async function selectProp(page: Page, key: string) {
  const prop = WORLD.props.find(item => item.key === key);
  if (!prop) throw new Error('Missing authored interaction');
  const point = await frameWorldProp(
    page,
    prop,
    id => en.world.zones[id as keyof typeof en.world.zones]
  );
  await page.mouse.move(point.x, point.y);
  await expect(page.getByRole('tooltip')).toHaveText(
    prop.kind === 'bed' ? en.world.poses.lie : en.world.poses.sit
  );
  await page.mouse.click(point.x, point.y);
}

test('scene seating is shared, survives reconnect, stands safely and keeps the bedroom private', async ({
  browser,
  baseURL,
}, info) => {
  if (!baseURL) throw new Error('Explicit isolated world host required');
  const contexts = await Promise.all([
    browser.newContext({
      baseURL,
      viewport: { width: 1280, height: 800 },
      serviceWorkers: 'block',
    }),
    browser.newContext({ baseURL, serviceWorkers: 'block' }),
  ]);
  const pages: Page[] = [];
  let latest: () => WorldView | null = () => null;
  try {
    for (let n = 0; n < contexts.length; n++) {
      const session = await contexts[n].request.post('/api/v1/world-proof/session', {
        headers: { Origin: new URL(baseURL).origin },
        data: { index: n === 0 ? 2 : 3 },
      });
      expect(session.status()).toBe(200);
      pages.push(await contexts[n].newPage());
    }
    const [page, peer] = pages;
    const own = observe(page),
      other = observe(peer);
    latest = own;
    const intents: unknown[] = [];
    page.on('websocket', socket =>
      socket.on('framesent', ({ payload }) => {
        const frame = JSON.parse(String(payload)) as {
          type: string;
          seq?: number;
          slot?: string | null;
        };
        if (frame.type === 'pose' || frame.type === 'move')
          intents.push({ type: frame.type, seq: frame.seq, slot: frame.slot });
      })
    );
    const fault = worldTransportFault();
    await fault.install(page);
    await enterNativeTransportPeer(peer, 'Pose observer');
    const errors: string[] = [],
      paid: string[] = [];
    page.on('pageerror', error => errors.push(error.name));
    page.on('request', request => {
      if (
        request.method() === 'POST' &&
        /agents\/chat|world\/messages\/(send|translate)(?:\?|$)/.test(request.url())
      )
        paid.push(request.url());
    });
    await page.bringToFront();
    await installOfflineFonts(page);
    await openNativeWorld(page, 'Seat visitor', worldProofUrl(baseURL, 'en'));
    await enterWorld(page);
    await expect.poll(() => own()?.status).toBe('active');
    if (!own()?.controlling)
      await page.getByRole('button', { name: 'Control from this tab' }).click();
    await selectProp(page, 'pond-bench');
    try {
      await expect.poll(() => own()?.you?.pose, { timeout: 20000 }).toMatch(/^pond-bench:/);
    } finally {
      await info.attach('motion-order', {
        body: JSON.stringify(intents),
        contentType: 'application/json',
      });
    }
    const seated = own()!.you!;
    await expect
      .poll(() => other()?.actors.find(actor => actor.id === seated.id)?.pose)
      .toBe(seated.pose);
    expect(seated.walking).toBe(false);
    await page.screenshot({ path: info.outputPath('garden-seat.png') });
    await fault.disconnect();
    await expect.poll(fault.connections).toBeGreaterThanOrEqual(2);
    await expect.poll(() => own()?.controlling && own()?.you?.pose).toBe(seated.pose);
    const canvas = page.locator('canvas.world-canvas');
    await canvas.focus();
    await page.keyboard.down('ArrowRight');
    await expect.poll(() => own()?.you?.pose).toBeNull();
    await page.keyboard.up('ArrowRight');
    expect(own()!.you!.position).not.toEqual(seated.position);
    await selectProp(page, 'home-bed');
    try {
      await expect.poll(() => own()?.you?.pose, { timeout: 30000 }).toBe('home-bed:0');
    } catch (error) {
      await page.screenshot({ path: info.outputPath('bed-before-cleanup.png') });
      await info.attach('pose-state', {
        body: JSON.stringify(own()),
        contentType: 'application/json',
      });
      throw error;
    }
    await expect.poll(() => other()?.actors.some(actor => actor.id === seated.id)).toBe(false);
    await page.screenshot({ path: info.outputPath('private-bed.png') });
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByRole('button', { name: /Stand up/ }).first()).toBeVisible();
    await page.screenshot({ path: info.outputPath('private-bed-phone.png') });
    await page
      .getByRole('button', { name: /Stand up/ })
      .first()
      .click();
    await expect.poll(() => own()?.you?.pose).toBeNull();
    expect(errors).toEqual([]);
    expect(paid).toEqual([]);
  } finally {
    if (pages[0]) {
      await pages[0].screenshot({ path: info.outputPath('before-cleanup.png') });
      await info.attach('last-world-view', {
        body: JSON.stringify(latest()),
        contentType: 'application/json',
      });
    }
    for (const page of pages) {
      if (page.isClosed()) continue;
      await page.evaluate(() => window.dispatchEvent(new Event('world-proof-leave')));
      const leave = page.getByRole('button', { name: 'Leave the world', exact: true });
      if (await leave.count()) await leave.last().click();
    }
    await Promise.all(contexts.map(context => context.close()));
  }
});
