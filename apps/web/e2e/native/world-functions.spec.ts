import { openNativeWorld, revealWorldControls } from '../fixtures/world-admission';
/** Native owner panel -> normal memory endpoint -> disposable PostgreSQL. */
import { test, expect, type BrowserContext, type Page, type Response } from './fixtures';
import AxeBuilder from '@axe-core/playwright';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { installOfflineFonts } from '../fixtures/offline-fonts';
import { worldProofUrl } from './world-route';
import { cssPixels } from './layout';
import { worldTransportFault } from './transport';
import { frameWorldProp } from '../fixtures/world-scene-navigation';
import { WORLD } from '../../src/features/world/definition';

function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}
function memoryItems(value: unknown): Array<{ id: string; content: string; pinned: boolean }> {
  if (!record(value) || !Array.isArray(value.items)) throw new Error('Missing native memory list');
  return value.items.map((item: unknown) => {
    if (
      !record(item) ||
      typeof item.id !== 'string' ||
      typeof item.content !== 'string' ||
      typeof item.pinned !== 'boolean'
    )
      throw new Error('Invalid native memory item');
    return { id: item.id, content: item.content, pinned: item.pinned };
  });
}
test('native functions: private memory read/pin, denied peer mutation and embedded LIA without implicit send', async ({
  browser,
  browserName,
  baseURL,
}, info) => {
  if (
    !baseURL ||
    ![
      '127.0.0.1',
      '127.0.0.3',
      'lia-world-functions-candidate',
      '127.0.0.5',
      'lia-world-polish-candidate',
      'lia-world-final-candidate',
      'lia-world-qualification-web',
      'lia-world-qualification-scroll',
      '127.0.0.7',
      '127.0.0.8',
      '127.0.0.6',
    ].includes(new URL(baseURL).hostname)
  )
    throw new Error('Independent functions host required');
  const identity =
    browserName === 'chromium'
      ? { index: 2, lng: 'en' }
      : browserName === 'firefox'
        ? { index: 4, lng: 'es' }
        : { index: 5, lng: 'it' };
  const locale: unknown = JSON.parse(
    readFileSync(join(__dirname, '../../locales', identity.lng, 'translation.json'), 'utf8')
  );
  const t = (path: string) => {
    let value: unknown = locale;
    for (const key of path.split('.')) value = record(value) ? value[key] : undefined;
    if (typeof value !== 'string') throw new Error('Missing authored label: ' + path);
    return value;
  };
  const origin = new URL(baseURL).origin;
  const contexts: BrowserContext[] = [];
  let memory: { id: string; pinned: boolean } | undefined;
  let activePage: Page | undefined;
  try {
    for (const index of [identity.index, 3]) {
      const context = await browser.newContext({
        baseURL,
        viewport: { width: 1280, height: 800 },
        serviceWorkers: 'block',
      });
      contexts.push(context);
      const login = await context.request.post('/api/v1/world-proof/session', {
        headers: { Origin: origin },
        data: { index },
      });
      expect(login.status()).toBe(200);
    }
    const [owner, other] = contexts;
    const before = await owner.request.get('/api/v1/memories');
    expect(before.status()).toBe(200);
    const items = memoryItems(await before.json());
    expect(items.length).toBeGreaterThan(0);
    memory = items[0];
    const otherBefore: unknown = await (await other.request.get('/api/v1/memories')).json();
    const page = await owner.newPage();
    const transport = worldTransportFault();
    await transport.install(page);
    activePage = page;
    await installOfflineFonts(page);
    const sends: string[] = [],
      errors: string[] = [];
    page.on('pageerror', error => errors.push(error.name));
    page.on('request', request => {
      if (request.method() === 'POST' && request.url().includes('/agents/chat/stream'))
        sends.push(request.url());
    });
    const url = worldProofUrl(baseURL, identity.lng);
    url.searchParams.set('intent', 'DO_NOT_SEND_WORLD_TEST');
    url.searchParams.set('draft', 'HOST_ONLY_TEST');
    url.searchParams.set('iid', 'host-only-world-test');
    await openNativeWorld(page, 'Native panel visitor', url);
    if (await page.locator('input[name="world-presence-consent"]').isVisible())
      await page.locator('input[name="world-presence-consent"]').check();
    await page.getByRole('button', { name: t('world.session.enter'), exact: true }).click();
    const functions = page.getByRole('button', { name: t('world.functions.title'), exact: true });
    const takeover = page.getByRole('button', { name: t('world.session.takeover'), exact: true });
    await expect(functions.or(takeover)).toBeVisible();
    if (await takeover.isVisible()) await takeover.click();
    await expect(functions).toBeEnabled();
    const nativeChunks: Promise<number>[] = [];
    const collectNativeChunk = (response: Response) => {
      if (
        response.request().resourceType() === 'script' &&
        new URL(response.url()).pathname.startsWith('/_next/static/chunks/')
      )
        nativeChunks.push(response.body().then(body => body.byteLength));
    };
    page.on('response', collectNativeChunk);
    await approachMemoryShelf(page, t);
    const panel = page.locator('#settings-section-memories');
    // The real authority must accept the walk from the courtyard into the home.
    await expect(panel).toBeVisible({ timeout: 30000 });
    await panel
      .getByRole('button', { name: new RegExp(t('memories.categories.preference')) })
      .click();
    await expect(panel.getByText(items[0].content, { exact: true })).toBeVisible();
    page.off('response', collectNativeChunk);
    const chunkSizes = await Promise.all(nativeChunks);
    expect(chunkSizes.length).toBeGreaterThan(0);
    // The delivery budget measures minified optimized chunks. Development
    // includes debugging/HMR code and is qualified for behavior separately.
    if (process.env.E2E_WORLD_NATIVE_OPTIMIZED === '1')
      expect(Math.max(...chunkSizes)).toBeLessThan(512 * 1024);
    const memoryVerified = page.waitForResponse(response => response.url().endsWith('/auth/me'));
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    expect((await memoryVerified).status()).toBe(200);
    await expect(panel.getByText(items[0].content, { exact: true })).toBeVisible();
    const pin = panel.getByRole('button', {
      name: t(memory.pinned ? 'memories.unpin' : 'memories.pin'),
      exact: true,
    });
    await transport.disconnect();
    await expect(
      page.getByRole('dialog', { name: t('world.session.reconnecting'), exact: true })
    ).toBeVisible();
    await page.keyboard.press('Escape');
    await expect.poll(transport.connections).toBeGreaterThanOrEqual(2);
    await expect(panel.getByText(items[0].content, { exact: true })).toBeVisible();
    await pin.click();
    await expect
      .poll(
        async () =>
          memoryItems(await (await owner.request.get('/api/v1/memories')).json()).find(
            item => item.id === memory?.id
          )?.pinned
      )
      .toBe(!memory.pinned);
    expect(await (await other.request.get('/api/v1/memories')).json()).toEqual(otherBefore);
    const denied = await other.request.patch(`/api/v1/memories/${memory.id}/pin`, {
      data: { pinned: memory.pinned },
    });
    expect(denied.status()).toBe(404);
    expect(
      memoryItems(await (await owner.request.get('/api/v1/memories')).json()).find(
        item => item.id === memory?.id
      )?.pinned
    ).toBe(!memory.pinned);
    await page.screenshot({ path: info.outputPath('world-native-memory.png') });
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(
      page
        .getByRole('dialog')
        .getByRole('heading', { name: t('memories.settings.title'), level: 2, exact: true })
    ).toBeInViewport();
    await expect(
      page.getByRole('dialog').getByRole('button', { name: t('common.close'), exact: true })
    ).toBeInViewport();
    expect(
      await page
        .getByRole('dialog')
        .getByRole('button', { name: t('common.close'), exact: true })
        .evaluate(button => {
          const bounds = button.getBoundingClientRect();
          const top = document.elementFromPoint(
            bounds.x + bounds.width / 2,
            bounds.y + bounds.height / 2
          );
          return top !== null && button.contains(top);
        })
    ).toBe(true);
    expect(
      (
        await new AxeBuilder({ page })
          .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
          .analyze()
      ).violations.map(item => ({
        id: item.id,
        nodes: item.nodes.map(node => ({ target: node.target, summary: node.failureSummary })),
      }))
    ).toEqual([]);
    await page.screenshot({ path: info.outputPath('world-native-memory-mobile.png') });
    await page.keyboard.press('Escape');
    await expect(page.locator('canvas.world-canvas')).toBeFocused();
    await revealWorldControls(page);
    await page.getByRole('button', { name: t('world.functions.talk'), exact: true }).click();
    await expect(
      page.getByRole('dialog', { name: t('world.functions.talk'), exact: true })
    ).toBeVisible();
    await expect(page.locator('[data-eyes-anchor-end]')).toBeVisible();
    expect(sends).toEqual([]);
    expect(
      await page
        .locator('textarea')
        .evaluateAll(elements =>
          elements.map(element => (element instanceof HTMLTextAreaElement ? element.value : ''))
        )
    ).not.toContain('HOST_ONLY_TEST');
    expect(new URL(page.url()).searchParams.get('intent')).toBe('DO_NOT_SEND_WORLD_TEST');
    const composer = page.locator('textarea');
    await expect(composer).toHaveCount(1);
    // This native proof deliberately has no compiled agent graph. Healthy chat
    // composition is covered by the hermetic world-LIA integration journey.
    await expect(composer).toBeDisabled();
    const verified = page.waitForResponse(response => response.url().endsWith('/auth/me'));
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    expect((await verified).status()).toBe(200);
    await expect(composer).toBeVisible();
    await expect(composer).toBeDisabled();
    expect(sends).toEqual([]);
    await page.screenshot({ path: info.outputPath('world-native-lia-mobile.png') });
    await page.keyboard.press('Escape');
    for (const button of await page.locator('.world-session-strip').getByRole('button').all()) {
      const bounds = await button.boundingBox();
      expect(cssPixels(bounds?.width)).toBeGreaterThanOrEqual(44);
      expect(cssPixels(bounds?.height)).toBeGreaterThanOrEqual(44);
    }
    await revealWorldControls(page);
    await page.getByRole('button', { name: t('world.session.leave'), exact: true }).click();
    expect(errors).toEqual([]);
  } catch (error) {
    if (activePage) await activePage.screenshot({ path: info.outputPath('before-cleanup.png') });
    throw error;
  } finally {
    try {
      for (const page of contexts[0]?.pages() ?? []) {
        await page.keyboard.press('Escape');
        const takeover = page.getByRole('button', {
          name: t('world.session.takeover'),
          exact: true,
        });
        if (await takeover.isVisible()) await takeover.click();
        const leave = page.getByRole('button', { name: t('world.session.leave'), exact: true });
        if (await leave.count()) {
          await revealWorldControls(page);
          await leave.last().click();
        }
      }
      if (contexts[0] && memory)
        await contexts[0].request.patch(`/api/v1/memories/${memory.id}/pin`, {
          data: { pinned: memory.pinned },
        });
    } finally {
      const closed = await Promise.allSettled(contexts.map(context => context.close()));
      expect(closed.filter(result => result.status === 'rejected')).toEqual([]);
    }
  }
});

/** Select the actual shelf pixels; no scripted teleport, catalogue or API bypass. */
async function approachMemoryShelf(page: Page, t: (path: string) => string): Promise<void> {
  const prop = WORLD.props.find(item => item.kind === 'archive' && item.activity === 'memories');
  if (!prop) throw new Error('Missing memory activity object');
  const point = await frameWorldProp(page, prop, id => t('world.zones.' + id));
  await page.mouse.move(point.x, point.y);
  await expect(page.getByRole('tooltip')).toHaveText(t('memories.settings.title'));
  await page.mouse.click(point.x, point.y);
}
