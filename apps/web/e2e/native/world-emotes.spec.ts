/** Two actual browser processes, native accounts and Redis; no socket or gesture doubles. */
import { test, expect, type BrowserContext, type Page } from './fixtures';
import AxeBuilder from '@axe-core/playwright';
import { openNativeWorld, enterWorld, revealWorldControls } from '../fixtures/world-admission';
import { installOfflineFonts } from '../fixtures/offline-fonts';
import { worldProofUrl } from './world-route';
import { signIn } from './world-arcade-helpers';
import en from '../../locales/en/translation.json';

function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}
function observe(page: Page, receipts: string[], sent: string[]) {
  page.on('websocket', socket => {
    if (!socket.url().endsWith('/world/ws')) return;
    socket.on('framesent', event => {
      const frame: unknown = JSON.parse(String(event.payload));
      if (record(frame) && frame.type === 'emote' && typeof frame.emote === 'string')
        sent.push(frame.emote);
    });
    socket.on('framereceived', event => {
      const frame: unknown = JSON.parse(String(event.payload));
      if (!record(frame) || frame.type !== 'snapshot' || !Array.isArray(frame.receipts)) return;
      for (const item of frame.receipts)
        if (record(item) && item.kind === 'emote' && typeof item.result === 'string') {
          if (!receipts.includes(item.result)) receipts.push(item.result);
        }
    });
  });
}
async function enter(
  context: BrowserContext,
  baseURL: string,
  index: number,
  receipts: string[],
  sent: string[]
) {
  await signIn(context, baseURL, index);
  const page = await context.newPage();
  observe(page, receipts, sent);
  await installOfflineFonts(page);
  await openNativeWorld(page, 'Gesture visitor', worldProofUrl(baseURL, 'en'));
  await enterWorld(page);
  await expect(page.locator('.world-admission')).not.toBeVisible();
  return page;
}
async function gesture(page: Page, name: string) {
  await revealWorldControls(page);
  await page.getByRole('button', { name: en.world.emotes.title, exact: true }).click();
  await page.getByRole('menuitem', { name: new RegExp(name) }).click();
  await expect(page.locator('canvas.world-canvas')).toBeFocused();
}

for (const width of [1280, 390])
  test(`finite gesture reaches an independent peer and expires at ${width}px`, async ({
    browser,
    baseURL,
  }, info) => {
    if (!baseURL) throw new Error('Disposable proof URL required');
    const peerEngine = await browser.browserType().launch({ headless: true });
    const senderContext = await browser.newContext({
      viewport: { width, height: 844 },
      serviceWorkers: 'block',
      reducedMotion: 'no-preference',
    });
    const receiverContext = await peerEngine.newContext({
      viewport: { width, height: 844 },
      serviceWorkers: 'block',
      reducedMotion: 'reduce',
    });
    try {
      const receipts: string[] = [];
      const sent: string[] = [];
      const peerReceipts: string[] = [];
      const sender = await enter(senderContext, baseURL, 8, receipts, sent);
      const receiver = await enter(receiverContext, baseURL, 7, peerReceipts, []);
      await gesture(sender, en.world.emotes.wave);
      // A burst inside the gesture interval stays in the page: nothing is
      // sent, the server never has to refuse it, and the sender is told why.
      await sender.locator('canvas.world-canvas').press('4');
      await expect(
        sender.getByRole('status').filter({ hasText: en.world.emotes.rate_limited })
      ).toHaveCount(1);
      await expect(receiver.locator('[data-world-emote="wave"]')).toHaveCount(1);
      await expect(receiver.locator('[data-world-emote="laugh"]')).toHaveCount(0);
      await receiver.screenshot({ path: info.outputPath('peer-wave.png') });
      await expect(receiver.locator('[data-world-emote="wave"]')).toHaveCount(0);
      await gesture(sender, en.world.emotes.thanks);
      await expect(receiver.locator('[data-world-emote="thanks"]')).toHaveCount(1);
      await expect(receiver.locator('[data-world-emote="thanks"]')).toHaveCount(0);
      expect(sent).toEqual(['wave', 'thanks']);
      expect(receipts).toEqual(['accepted']);
      expect(peerReceipts).toEqual([]);
      expect((await new AxeBuilder({ page: sender }).analyze()).violations).toEqual([]);
      expect((await new AxeBuilder({ page: receiver }).analyze()).violations).toEqual([]);
      await info.attach('gesture-proof.json', {
        body: JSON.stringify({
          width,
          independentBrowserProcesses: true,
          gestures: ['wave', 'thanks'],
          reducedPeer: true,
        }),
        contentType: 'application/json',
      });
    } finally {
      await senderContext.close();
      await receiverContext.close();
      await peerEngine.close();
    }
  });
