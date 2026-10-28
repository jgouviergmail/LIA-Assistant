import { openNativeWorld, revealWorldControls } from '../fixtures/world-admission';
/** Real standalone dashboard and native inert accounts; no application API doubles. */
import { test, expect, type Browser, type BrowserContext, type Page } from '../native/fixtures';
import AxeBuilder from '@axe-core/playwright';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { installOfflineFonts } from '../fixtures/offline-fonts';
import { enterNativeTransportPeer } from '../fixtures/world-native-peer';

function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}
function labels(lng: string): (key: string) => string {
  const locale: unknown = JSON.parse(
    readFileSync(join(__dirname, '../../locales', lng, 'translation.json'), 'utf8')
  );
  return key => {
    let value = locale;
    for (const part of key.split('.')) value = record(value) ? value[part] : undefined;
    if (typeof value !== 'string') throw new Error('Missing native label: ' + key);
    return value;
  };
}

test('standalone: native menu, five server clients and per-device rendering', async ({
  browser,
  browserName,
  baseURL,
}, info) => {
  if (
    !baseURL ||
    ![
      '127.0.0.1',
      '127.0.0.7',
      'lia-world-final-production',
      'lia-world-qualification-production',
      'lia-world-qualification-scroll',
    ].includes(new URL(baseURL).hostname)
  )
    throw new Error('Independent optimized host required');
  const origin = new URL(baseURL).origin;
  const people: Array<{ context: BrowserContext; page: Page; t: (key: string) => string }> = [];
  const extraBrowsers: Browser[] = [];
  const errors: string[] = [],
    paid: string[] = [];
  const samples: Array<Record<string, unknown>> = [];
  let publicPeople = 0;
  let failed = false;
  let stage = 'setup';

  async function enter(index: number): Promise<void> {
    // Independent browser processes keep their own foreground tab, as five
    // separate users would. Nothing overrides document visibility or authority.
    const engine = index === 3 ? browser : await browser.browserType().launch({ headless: true });
    if (engine !== browser) extraBrowsers.push(engine);
    const context = await engine.newContext({
      baseURL,
      viewport: { width: 1280, height: 800 },
      serviceWorkers: 'block',
    });
    const page = await context.newPage();
    const lng = ['fr', 'en', 'de', 'es', 'it'][index - 1];
    const t = labels(lng);
    people.push({ context, page, t });
    await installOfflineFonts(page);
    page.on('pageerror', error => errors.push(error.name));
    page.on('request', request => {
      if (/\/(agents\/chat\/stream|world\/messages\/send)/.test(request.url()))
        paid.push(new URL(request.url()).pathname);
    });
    if (index === 3)
      page.on('websocket', socket => {
        if (!socket.url().endsWith('/world/ws')) return;
        socket.on('framereceived', frame => {
          const value: unknown = JSON.parse(String(frame.payload));
          if (record(value) && value.type === 'snapshot' && Array.isArray(value.actors))
            publicPeople = value.actors.length;
        });
      });
    const login = await context.request.post('/api/v1/world-proof/session', {
      headers: { Origin: origin },
      data: { index },
    });
    expect(login.status()).toBe(200);
    if (index !== 3) {
      await enterNativeTransportPeer(page, `Production ${index}`);
      return;
    }
    await openNativeWorld(page, `Production ${index}`, `/${lng}/dashboard/world`);
    if (await page.locator('input[name="world-presence-consent"]').isVisible())
      await page.locator('input[name="world-presence-consent"]').check();
    await page.getByRole('button', { name: t('world.session.enter'), exact: true }).click();
    const functions = page.getByRole('button', { name: t('world.functions.title'), exact: true });
    const takeover = page.getByRole('button', { name: t('world.session.takeover'), exact: true });
    await expect(functions.or(takeover)).toBeVisible();
    if (await takeover.isVisible()) await takeover.click();
    await expect(functions).toBeEnabled();
  }

  async function sample(page: Page, profile: string): Promise<void> {
    await page.waitForTimeout(6000); // Deliberate visible frame-sampling window.
    const fps = Number((await page.locator('[data-world-fps]').innerText()).replace(',', '.'));
    expect(fps).toBeGreaterThan(0);
    expect(publicPeople).toBe(4);
    for (const person of people) {
      if (person.page !== page)
        await expect(person.page.locator('html')).toHaveAttribute(
          'data-world-native-peer',
          'active'
        );
    }
    samples.push({
      profile,
      browserName,
      viewport: page.viewportSize(),
      zoom: (await page.locator('[data-world-zoom]').textContent())?.trim() ?? null,
      fps,
      textures: await page.locator('.world-metrics dd').nth(3).innerText(),
      frameP95: await page.locator('[data-world-frame]').innerText(),
      renderP95: await page.locator('[data-world-render]').innerText(),
      phase: await page.locator('[data-world-phase]').getAttribute('data-world-phase'),
      weather: await page.locator('[data-world-weather]').getAttribute('data-world-weather'),
      clients: 5,
      independentHeadlessBrowsers: true,
      fullUIRenderers: 1,
      physicalDevice: false,
    });
  }
  try {
    const anonymous = await browser.newContext({ baseURL });
    try {
      expect((await anonymous.request.get('/en/world-preview')).status()).toBe(404);
    } finally {
      await anonymous.close();
    }
    for (let index = 1; index <= 5; index++) await enter(index);
    stage = 'desktop measurement';
    const { page, t } = people[2];
    await page.bringToFront();
    await expect.poll(() => publicPeople).toBe(4);
    await expect(page.locator('[data-companion-presence]')).toHaveCount(0);
    await expect(
      page.getByRole('link', { name: t('navigation.world'), exact: true }).first()
    ).toBeVisible();
    await page.getByRole('button', { name: t('world.metrics'), exact: true }).click();
    await sample(page, 'desktop: five native server clients, one full UI renderer');
    await page.screenshot({ path: info.outputPath('production-desktop.png') });
    await page.getByRole('button', { name: t('world.close_metrics'), exact: true }).click();
    await page.setViewportSize({ width: 390, height: 844 });
    stage = 'phone controls';
    await revealWorldControls(page);
    await page.getByRole('button', { name: t('world.help'), exact: true }).click();
    await page.getByRole('combobox', { name: t('world.quality') }).selectOption('balanced');
    await page.getByRole('button', { name: t('world.play'), exact: true }).click();
    await page.getByRole('button', { name: t('world.metrics'), exact: true }).click();
    await sample(page, 'phone viewport, balanced quality');
    await page.getByRole('button', { name: t('world.close_metrics'), exact: true }).click();
    for (const button of await page.locator('.world-session-strip').getByRole('button').all()) {
      if (await button.isEnabled()) await button.click({ trial: true });
    }
    await page.getByRole('button', { name: t('world.help'), exact: true }).click();
    await page.getByRole('combobox', { name: t('world.quality') }).selectOption('low');
    await page.getByRole('button', { name: t('world.play'), exact: true }).click();
    await page.getByRole('button', { name: t('world.metrics'), exact: true }).click();
    await sample(page, 'phone viewport, economic quality');
    stage = 'touch gestures';
    if (browserName === 'chromium') {
      // Metrics are an interactive overlay, not walkable/touchable ground.
      await page.getByRole('button', { name: t('world.close_metrics'), exact: true }).click();
      const toolbar = page.locator('.world-hud-toggle');
      if ((await toolbar.getAttribute('aria-expanded')) === 'true') await toolbar.click();
      const client = await page.context().newCDPSession(page);
      try {
        await client.send('Emulation.setTouchEmulationEnabled', {
          enabled: true,
          maxTouchPoints: 2,
        });
        const zoom = (await page.locator('[data-world-zoom]').textContent())?.trim() ?? '';
        expect(zoom).toMatch(/^\d+%$/);
        expect(
          await page
            .locator('canvas.world-canvas')
            .evaluate(canvas => [140, 230].every(x => document.elementFromPoint(x, 350) === canvas))
        ).toBe(true);
        const touch = (x: number, id: number) => ({ x, y: 350, id, radiusX: 3, radiusY: 3 });
        await client.send('Input.dispatchTouchEvent', {
          type: 'touchStart',
          touchPoints: [touch(140, 1), touch(230, 2)],
        });
        await client.send('Input.dispatchTouchEvent', {
          type: 'touchMove',
          touchPoints: [touch(110, 1), touch(260, 2)],
        });
        await client.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
        const expectedZoom = Math.round((Number.parseInt(zoom, 10) * 150) / 90);
        await expect(page.locator('[data-world-zoom]')).toHaveText(`${expectedZoom}%`);
        await revealWorldControls(page);
        await page.getByRole('button', { name: t('world.metrics'), exact: true }).click();
        await client.send('Emulation.setCPUThrottlingRate', { rate: 4 });
        await sample(page, 'phone viewport, economic quality, CPU slowdown 4x');
      } finally {
        await client.send('Emulation.setCPUThrottlingRate', { rate: 1 });
        await client.detach();
      }
    }
    await page.getByRole('button', { name: t('world.close_metrics'), exact: true }).click();
    stage = 'phone accessibility';
    const scan = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(
      scan.violations.map(item => ({ id: item.id, targets: item.nodes.map(node => node.target) }))
    ).toEqual([]);
    await page.screenshot({ path: info.outputPath('production-mobile.png') });
    stage = 'native navigation';
    await page.getByRole('button', { name: t('world.session.leave'), exact: true }).click();
    await page.setViewportSize({ width: 1280, height: 800 });
    await page
      .getByRole('link', { name: t('navigation.chat'), exact: true })
      .first()
      .click();
    await expect(page).toHaveURL(/dashboard\/chat/);
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    await page
      .getByRole('link', { name: t('navigation.world'), exact: true })
      .first()
      .click();
    await expect(page.locator('[data-world-public-name]')).toBeVisible();
    expect(paid).toEqual([]);
    expect(errors).toEqual([]);
  } catch (error) {
    failed = true;
    console.info(`Optimized world interrupted at: ${stage}`);
    throw error;
  } finally {
    const cleanup: string[] = [];
    try {
      for (const { context, page, t } of people) {
        try {
          await page.evaluate(() => window.dispatchEvent(new Event('world-proof-leave')));
          await page.bringToFront();
          await page.keyboard.press('Escape');
          const leave = page.getByRole('button', { name: t('world.session.leave'), exact: true });
          if (await leave.last().isVisible()) await leave.last().click({ timeout: 3000 });
        } catch {
          cleanup.push('owned actor could not explicitly leave');
        } finally {
          await context.close();
        }
      }
    } finally {
      await Promise.all(extraBrowsers.map(engine => engine.close()));
      await info.attach('production-performance.json', {
        body: JSON.stringify(samples),
        contentType: 'application/json',
      });
    }
    if (!failed) expect(cleanup).toEqual([]);
  }
});
