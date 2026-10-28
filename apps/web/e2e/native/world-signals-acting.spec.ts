/** Real World/socket/notification authority, fixed provider-free activity evidence. */
import { test, expect, type BrowserContext, type Page } from './fixtures';
import AxeBuilder from '@axe-core/playwright';
import { openNativeWorld, enterWorld, revealWorldControls } from '../fixtures/world-admission';
import { installOfflineFonts } from '../fixtures/offline-fonts';
import { chatRoutes } from '../fixtures/chat';
import { frameWorldProp } from '../fixtures/world-scene-navigation';
import { worldProofUrl } from './world-route';
import { signIn } from './world-arcade-helpers';
import { WORLD } from '../../src/features/world/definition';
import en from '../../locales/en/translation.json';

async function open(context: BrowserContext, baseURL: string, index: number, frames?: string[]) {
  await signIn(context, baseURL, index);
  const page = await context.newPage();
  if (frames)
    page.on('websocket', socket => {
      if (socket.url().endsWith('/world/ws'))
        socket.on('framereceived', event => frames.push(String(event.payload)));
    });
  await installOfflineFonts(page);
  await openNativeWorld(page, 'Signals visitor', worldProofUrl(baseURL, 'en'));
  await enterWorld(page);
  await expect(page.locator('.world-admission')).not.toBeVisible();
  await expect(page.locator('.world-device-controls')).toHaveAttribute(
    'data-notifications-connected',
    'true'
  );
  return page;
}
async function phone(page: Page, reminders: number) {
  await revealWorldControls(page);
  // Expand the folded tools only: a second click on an open toggle folds them away.
  const toggle = page.locator('.world-device-toggle');
  if ((await toggle.isVisible()) && (await toggle.getAttribute('aria-expanded')) === 'false')
    await toggle.click();
  return page.getByRole('button', {
    name: en.world.device.phone.replace('{{sms}}', '0').replace('{{reminders}}', String(reminders)),
    exact: true,
  });
}
for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
]) {
  test(`private reminder badge opens the native reader and shares phone acknowledgment without socket disclosure at ${viewport.width}px`, async ({
    browser,
    baseURL,
  }, info) => {
    if (!baseURL) throw new Error('Disposable proof URL required');
    const context = await browser.newContext({
      viewport,
      serviceWorkers: 'block',
    });
    try {
      const frames: string[] = [];
      const page = await open(context, baseURL, 8, frames);
      const response = await context.request.post('/api/v1/world-proof/reminder', {
        headers: { Origin: new URL(baseURL).origin },
      });
      expect(response.status()).toBe(204);
      await expect(await phone(page, 1)).toBeVisible();
      const peer = await browser.newContext({
        viewport: { width: 1280, height: 800 },
        serviceWorkers: 'block',
      });
      try {
        const other = await open(peer, baseURL, 2);
        await expect(await phone(other, 0)).toBeVisible();
        expect(await other.getByText('PRIVATE_WORLD_REMINDER').count()).toBe(0);
      } finally {
        await peer.close();
      }
      await page.bringToFront();
      const alarm = WORLD.props.find(
        prop => prop.kind === 'alarm' && prop.activity === 'reminders'
      );
      if (!alarm) throw new Error('Missing reminder support');
      const point = await frameWorldProp(
        page,
        alarm,
        id => en.world.zones[id as keyof typeof en.world.zones]
      );
      const zoom =
        Number((await page.locator('[data-world-zoom]').innerText()).replace('%', '')) / 100;
      const toolbar = page.locator('.world-hud-toggle');
      if ((await toolbar.isVisible()) && (await toolbar.getAttribute('aria-expanded')) === 'true')
        await toolbar.click();
      const badge = { x: point.x + 13 * zoom, y: point.y - (alarm.height * 16 + 6) * zoom };
      expect(
        await page.evaluate(
          ({ x, y }) =>
            document.elementFromPoint(x, y) === document.querySelector('canvas.world-canvas'),
          badge
        )
      ).toBe(true);
      await page.mouse.move(badge.x, badge.y);
      await expect(page.locator('.world-object-hint')).toContainText(en.reminders.settings.title);
      await page.screenshot({ path: info.outputPath('private-reminder-badge.png') });
      await page.mouse.click(badge.x, badge.y);
      await expect(page.getByText('PRIVATE_WORLD_REMINDER', { exact: true })).toBeVisible({
        timeout: 30000,
      });
      await expect(page.getByRole('dialog', { name: en.world.device.title })).toBeVisible();
      expect(
        (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
          .violations
      ).toEqual([]);
      await page.screenshot({ path: info.outputPath('private-reminder-reader.png') });
      await page.keyboard.press('Escape');
      await expect(page.locator('canvas.world-canvas')).toBeFocused();
      await expect(await phone(page, 0)).toBeVisible();
      expect(frames.some(frame => frame.includes('"snapshot"'))).toBe(true);
      expect(frames.join('')).not.toContain('PRIVATE_WORLD_REMINDER');
    } finally {
      await context.close();
    }
  });
}

for (const width of [1280, 390]) {
  test(`embedded native chat drives creating, prepared, confirmed success, failure and waiting at ${width}px without a provider`, async ({
    browser,
    baseURL,
  }, info) => {
    if (!baseURL) throw new Error('Disposable proof URL required');
    const context = await browser.newContext({
      viewport: { width, height: 844 },
      serviceWorkers: 'block',
      reducedMotion: 'reduce',
    });
    try {
      const page = await context.newPage();
      for (const route of chatRoutes([]).filter(route => route.method !== 'POST'))
        await page.route(route.url, handler => handler.fulfill({ json: route.json }));
      await page.route('**/api/v1/agents/chat/stream', route =>
        route.continue({ url: new URL('/api/v1/world-proof/acting', baseURL).href })
      );
      await signIn(context, baseURL, 8);
      await installOfflineFonts(page);
      await openNativeWorld(page, 'Acting visitor', worldProofUrl(baseURL, 'en'));
      await enterWorld(page);
      await revealWorldControls(page);
      await page.getByRole('button', { name: en.world.call_bip, exact: true }).click();
      await page.getByRole('button', { name: en.world.functions.talk, exact: true }).click();
      const composer = page.locator('textarea');
      const acting = page.locator('.world-conversation [data-world-acting]');
      await expect(acting).toBeVisible();
      await expect(composer).toBeEnabled();
      for (const [message, state] of [
        ['WORLD_PREPARED', 'prepared'],
        ['WORLD_SUCCEEDED', 'success'],
        ['WORLD_FAILED', 'error'],
        ['WORLD_WAITING', 'waiting'],
      ]) {
        await composer.fill(message);
        await composer.press('Enter');
        await expect(acting).toHaveAttribute('data-world-acting', 'creating');
        await expect(acting).toHaveAttribute('data-world-acting', state);
        await expect(acting).toBeVisible();
        await expect(composer).toBeEnabled();
        await page.screenshot({ path: info.outputPath('acting-' + state + '.png') });
      }
      await page.keyboard.press('Escape');
      await expect(
        page.getByRole('button', { name: en.world.functions.talk, exact: true })
      ).toBeFocused();
    } finally {
      await context.close();
    }
  });
}
