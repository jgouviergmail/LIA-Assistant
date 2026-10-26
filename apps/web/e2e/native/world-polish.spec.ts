import { openNativeWorld } from '../fixtures/world-admission';
import { createWorldDevice, closeWorldDevices, type WorldDevice } from '../fixtures/world-device';
/** Native no-send, passive owner weather and a bounded private peer gallery. */
import { test, expect, type BrowserContext, type Page } from './fixtures';
import AxeBuilder from '@axe-core/playwright';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { installOfflineFonts } from '../fixtures/offline-fonts';
import { worldProofUrl } from './world-route';
import { cssPixels } from './layout';

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
    if (typeof value !== 'string') throw new Error('Missing authored label: ' + key);
    return value;
  };
}

test('polished world: personal cached atmosphere, E interaction, native draft, private paged peers and reachable mobile HUD', async ({
  browser,
  baseURL,
}, info) => {
  if (
    !baseURL ||
    ![
      '127.0.0.1',
      '127.0.0.5',
      'lia-world-polish-candidate',
      '127.0.0.6',
      'lia-world-final-candidate',
      '127.0.0.7',
      'lia-world-final-production',
      'lia-world-qualification-production',
      'lia-world-qualification-web',
      'lia-world-qualification-scroll',
    ].includes(new URL(baseURL).hostname)
  )
    throw new Error('Independent polish proof host required');
  const origin = new URL(baseURL).origin;
  const t = labels('fr');
  const contexts: BrowserContext[] = [];
  const devices: WorldDevice[] = [];
  const failures: string[] = [];
  const paid: string[] = [];
  const ambientFetches: string[] = [];
  let scope: { epoch: string; controller: string } | null = null;
  function capturedScope(): { epoch: string; controller: string } | null {
    return scope;
  }
  let resume: string | null = null;
  async function open(index: number, lng: string, alias: string): Promise<Page> {
    const device = await createWorldDevice(browser, {
      baseURL,
      viewport: { width: 1280, height: 800 },
      serviceWorkers: 'block',
    });
    devices.push(device);
    const context = device.context;
    contexts.push(context);
    const session = await context.request.post('/api/v1/world-proof/session', {
      headers: { Origin: origin },
      data: { index },
    });
    expect(session.status()).toBe(200);
    const page = await context.newPage();
    await page.bringToFront();
    await installOfflineFonts(page);
    page.on('pageerror', error => failures.push(error.name));
    page.on('request', request => {
      if (
        request.url().includes('/agents/chat/stream') ||
        request.url().includes('/world/messages/send')
      )
        paid.push(new URL(request.url()).pathname);
      if (/\/briefing\/(cards|synthesis|refresh)/.test(request.url()))
        ambientFetches.push(new URL(request.url()).pathname);
    });
    if (index === 1)
      page.on('websocket', socket => {
        if (!socket.url().endsWith('/world/ws')) return;
        socket.on('framereceived', event => {
          const value: unknown = JSON.parse(String(event.payload));
          if (!record(value)) return;
          if (value.type === 'ready' && typeof value.resume === 'string') resume = value.resume;
          if (value.type === 'snapshot' && typeof value.epoch === 'string' && resume)
            scope = { epoch: value.epoch, controller: resume };
          if (
            String(event.payload).includes('PRIVATE_FIXTURE_LOCATION') ||
            String(event.payload).includes('Atelier ')
          )
            failures.push('owner-projection-in-shared-snapshot');
        });
      });
    const url = worldProofUrl(origin, lng);
    url.searchParams.set('draft', 'HOST_ONLY');
    url.searchParams.set('intent', 'NEVER_SEND');
    url.searchParams.set('iid', 'polish-host-only');
    await openNativeWorld(page, alias, url);
    const copy = labels(lng);
    if (await page.locator('input[name="world-presence-consent"]').isVisible())
      await page.locator('input[name="world-presence-consent"]').check();
    await page.getByRole('button', { name: copy('world.session.enter'), exact: true }).click();
    const functions = page.getByRole('button', {
      name: copy('world.functions.title'),
      exact: true,
    });
    const takeover = page.getByRole('button', {
      name: copy('world.session.takeover'),
      exact: true,
    });
    await expect(functions.or(takeover)).toBeVisible();
    if (await takeover.isVisible()) await takeover.click();
    await expect(functions).toBeEnabled();
    return page;
  }
  try {
    const page = await open(1, 'fr', 'Camille');
    const canvas = page.locator('canvas');
    await expect(page.locator('[data-world-weather]')).toHaveAttribute(
      'data-world-weather',
      'rain'
    );
    const environment = await contexts[0].request.get('/api/v1/world/environment');
    expect(environment.status()).toBe(200);
    expect(await environment.text()).not.toContain('PRIVATE_');
    await canvas.focus();
    await page.keyboard.press('e');
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(canvas).toBeFocused();
    await page.getByRole('button', { name: t('world.functions.title'), exact: true }).click();
    await page.getByRole('menuitem', { name: t('world.functions.title'), exact: true }).click();
    await page
      .getByRole('searchbox', { name: t('world.functions.search') })
      .fill(t('chat.slash.agenda_label'));
    await page
      .getByRole('button')
      .filter({ has: page.getByText(t('chat.slash.agenda_label'), { exact: true }) })
      .click();
    await expect(page.locator('textarea')).toHaveValue(t('chat.slash.agenda_intent'));
    expect(paid).toEqual([]);
    await page.screenshot({ path: info.outputPath('world-native-action.png') });
    await page.keyboard.press('Escape');
    const other = await open(2, 'en', 'Robin');
    await page.bringToFront();
    await page.getByRole('button', { name: t('world.functions.title'), exact: true }).click();
    await page.getByRole('menuitem', { name: t('settings.peers.title'), exact: true }).click();
    await expect(page.getByRole('article').first()).toBeVisible();
    const first = await page.getByRole('article').getByRole('heading').allTextContents();
    const firstPresence = await page
      .locator('[data-world-peer-presence]')
      .evaluateAll(nodes => nodes.map(node => node.getAttribute('data-world-peer-presence')));
    expect(first.length).toBeLessThanOrEqual(12);
    await page.getByRole('button', { name: t('world.peers.next'), exact: true }).click();
    await expect(
      page.getByRole('button', { name: t('world.peers.first'), exact: true })
    ).toBeVisible();
    await expect(page.getByRole('article').first()).toBeVisible();
    const second = await page.getByRole('article').getByRole('heading').allTextContents();
    const secondPresence = await page
      .locator('[data-world-peer-presence]')
      .evaluateAll(nodes => nodes.map(node => node.getAttribute('data-world-peer-presence')));
    const names = [...first, ...second];
    expect(new Set(names).size).toBe(names.length);
    // Another native journey's visible actor can retain its short reconnect
    // lease. Every authored non-playing connection must still appear exactly once.
    expect(names.filter(name => name.startsWith('Atelier ')).sort()).toEqual(
      Array.from({ length: 17 }, (_, index) => `Atelier ${String(index + 1).padStart(2, '0')}`)
    );
    expect([...first, ...second]).not.toContain('Proof 2');
    const presence = new Map(
      names.map((name, index) => [name, [...firstPresence, ...secondPresence][index]])
    );
    expect(presence.get('Robin')).toBe('online');
    for (const name of names.filter(name => name.startsWith('Atelier ')))
      expect(presence.get(name)).toBe('offline');
    expect(await page.getByRole('dialog').textContent()).not.toContain('@');
    const ownedScope = capturedScope();
    if (!ownedScope) throw new Error('Missing private controller authority');
    const denied = await contexts[1].request.post('/api/v1/world/messages/peers', {
      data: { ...ownedScope },
    });
    expect(denied.status()).toBe(403);
    expect(await denied.text()).not.toContain('Atelier');
    await page.screenshot({ path: info.outputPath('world-peer-gallery.png') });
    await page.keyboard.press('Escape');
    await canvas.focus();
    await page.keyboard.down('ArrowDown');
    await page.waitForTimeout(500); // Bounded held human input, not an infrastructure wait.
    await page.keyboard.up('ArrowDown');
    await page.getByRole('button', { name: t('world.call_bip'), exact: true }).click();
    await expect(
      page.getByRole('button', { name: t('world.call_bip'), exact: true })
    ).toHaveAttribute('aria-pressed', 'true');
    await page.screenshot({ path: info.outputPath('world-scene-desktop.png') });
    for (const size of [
      { width: 390, height: 844 },
      { width: 844, height: 390 },
      { width: 320, height: 568 },
    ]) {
      await page.setViewportSize(size);
      for (const button of await page.locator('.world-session-strip').getByRole('button').all()) {
        await expect(button).toBeInViewport();
        if (await button.isEnabled()) await button.click({ trial: true });
        const bounds = await button.boundingBox();
        expect(cssPixels(bounds?.width)).toBeGreaterThanOrEqual(44);
        expect(cssPixels(bounds?.height)).toBeGreaterThanOrEqual(44);
      }
      const violations = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze();
      expect(
        violations.violations.map(item => ({
          id: item.id,
          targets: item.nodes.map(node => node.target),
        }))
      ).toEqual([]);
      await page.screenshot({
        path: info.outputPath(`world-scene-${size.width}-${size.height}.png`),
      });
    }
    expect(await other.title()).toBeTruthy();
    expect(paid).toEqual([]);
    expect(ambientFetches).toEqual([]);
    expect(failures).toEqual([]);
  } finally {
    try {
      for (const [index, context] of contexts.entries()) {
        for (const page of context.pages()) {
          await page.bringToFront();
          await page.keyboard.press('Escape');
          const leave = page.getByRole('button', {
            name: labels(index === 0 ? 'fr' : 'en')('world.session.leave'),
            exact: true,
          });
          if (await leave.count()) await leave.last().click();
        }
      }
    } finally {
      await closeWorldDevices(devices);
    }
  }
});
