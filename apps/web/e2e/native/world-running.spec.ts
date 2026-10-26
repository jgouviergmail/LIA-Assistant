import { openNativeWorld } from '../fixtures/world-admission';
/** The actual double click reaches native movement authority, with no client-chosen speed. */
import { expect, test } from './fixtures';
import en from '../../locales/en/translation.json';
import { MOVEMENT } from '../../src/features/world/movement';
import { installOfflineFonts } from '../fixtures/offline-fonts';
import { worldProofUrl } from './world-route';

test('a double click runs through authoritative collision-safe movement at a bounded speed', async ({
  browser,
  baseURL,
}) => {
  if (!baseURL) throw new Error('Isolated host required');
  const context = await browser.newContext({
    baseURL,
    viewport: { width: 1280, height: 800 },
    serviceWorkers: 'block',
  });
  const page = await context.newPage();
  const steps: number[] = [],
    intents: boolean[] = [],
    errors: string[] = [];
  let previous: { ack: number; x: number; y: number } | null = null;
  page.on('pageerror', e => errors.push(e.name));
  page.on('websocket', socket => {
    if (!socket.url().endsWith('/world/ws')) return;
    socket.on('framesent', ({ payload }) => {
      const f = JSON.parse(String(payload)) as { type: string; running?: boolean };
      if (f.type === 'move') intents.push(f.running === true);
    });
    socket.on('framereceived', ({ payload }) => {
      const f = JSON.parse(String(payload)) as {
        type: string;
        ack: number;
        you?: { position: { x: number; y: number } };
      };
      if (f.type !== 'snapshot' || !f.you) return;
      const p = f.you.position;
      if (previous && f.ack > previous.ack)
        steps.push(Math.hypot(p.x - previous.x, p.y - previous.y) / (f.ack - previous.ack));
      previous = { ack: f.ack, ...p };
    });
  });
  try {
    expect(
      (
        await context.request.post('/api/v1/world-proof/session', {
          headers: { Origin: new URL(baseURL).origin },
          data: { index: 8 },
        })
      ).status()
    ).toBe(200);
    await installOfflineFonts(page);
    await openNativeWorld(page, 'Running visitor', worldProofUrl(baseURL, 'en'));
    if (await page.locator('input[name="world-presence-consent"]').isVisible())
      await page.locator('input[name="world-presence-consent"]').check();
    await page.getByRole('button', { name: en.world.session.enter, exact: true }).click();
    await expect.poll(() => previous !== null).toBe(true);
    const box = await page.locator('canvas.world-canvas').boundingBox();
    if (!box) throw new Error('Missing game canvas');
    const zoom =
      Number((await page.locator('[data-world-zoom]').innerText()).replace('%', '')) / 100;
    // The clear central aisle extends straight from the arrival point towards the terrace.
    await page.mouse.dblclick(
      box.x + box.width / 2 - 32 * 8 * zoom,
      box.y + box.height / 2 + 16 * 8 * zoom
    );
    await expect.poll(() => intents.includes(true)).toBe(true);
    await expect.poll(() => steps.some(d => d > 0.4)).toBe(true);
    expect(steps.every(d => d <= MOVEMENT.run * 0.1 + 0.001)).toBe(true);
    expect(errors).toEqual([]);
  } finally {
    await page.keyboard.press('Escape');
    const leave = page.getByRole('button', { name: en.world.session.leave, exact: true });
    if (await leave.count()) await leave.last().click();
    await context.close();
  }
});
