import { openNativeWorld, revealWorldControls, enterWorld } from '../fixtures/world-admission';
/** Native cookie/SQL home save, conflict and private input; no business/provider doubles. */
import { test, expect, type BrowserContext, type Page } from './fixtures';
import AxeBuilder from '@axe-core/playwright';
import { installOfflineFonts } from '../fixtures/offline-fonts';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { worldProofUrl } from './world-route';

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
function revision(value: unknown): number {
  if (
    !record(value) ||
    !record(value.preferences) ||
    typeof value.preferences.revision !== 'number'
  )
    throw new Error('Missing native home revision');
  return value.preferences.revision;
}

test('private home: real save, cancel, conflict/reload, phone accessibility and owner isolation', async ({
  browser,
  baseURL,
  browserName,
}, info) => {
  if (
    !baseURL ||
    ![
      'lia-world-home-candidate',
      'lia-world-functions-candidate',
      'lia-world-polish-candidate',
      'lia-world-final-candidate',
      'lia-world-qualification-web',
      'lia-world-qualification-scroll',
      '127.0.0.1',
      '127.0.0.7',
      '127.0.0.8',
      '127.0.0.2',
      '127.0.0.3',
      '127.0.0.5',
      '127.0.0.6',
    ].includes(new URL(baseURL).hostname)
  )
    throw new Error('Home proof requires its independent home preview');
  const origin = new URL(baseURL).origin;
  // Independent accounts respect the native write limit across the engine
  // matrix, and exercise canonical localized controls rather than raising it.
  const identity =
    browserName === 'chromium'
      ? { index: 2, lng: 'en' }
      : browserName === 'firefox'
        ? { index: 4, lng: 'es' }
        : { index: 5, lng: 'it' };
  const locale: unknown = JSON.parse(
    readFileSync(join(__dirname, '../../locales', identity.lng, 'translation.json'), 'utf8')
  );
  function translated(...path: string[]): string {
    let current: unknown = locale;
    for (const key of path) current = record(current) ? current[key] : undefined;
    if (typeof current !== 'string') throw new Error('Missing authored proof label');
    return current;
  }
  const homeLabel = (...path: string[]) => translated('world', 'home', ...path);
  const sessionLabel = (key: string) => translated('world', 'session', key);
  const contexts: BrowserContext[] = [];
  const escaped: string[] = [];
  const errors: string[] = [];
  let active: BrowserContext | undefined;
  let canReset = false;
  try {
    for (const index of [identity.index, 3]) {
      const context = await browser.newContext({
        baseURL,
        viewport: { width: 1280, height: 800 },
        serviceWorkers: 'block',
      });
      contexts.push(context);
      await context.route('**/*', route => {
        const url = new URL(route.request().url());
        if (url.origin === origin) return route.continue();
        escaped.push(url.origin);
        return route.abort();
      });
      const login = await context.request.post('/api/v1/world-proof/session', {
        headers: { Origin: origin },
        data: { index },
      });
      expect(login.status()).toBe(200);
    }
    const [owner, other] = contexts;
    active = owner;
    const initial = await owner.request.get('/api/v1/world/home');
    expect(initial.status()).toBe(200);
    expect(initial.headers()['cache-control']).toBe('no-store');
    const initialData: unknown = await initial.json();
    revision(initialData);
    canReset = true;
    const otherBefore: unknown = await (await other.request.get('/api/v1/world/home')).json();
    const reset = await owner.request.put('/api/v1/world/home', {
      data: { expected_revision: revision(initialData), reset: true },
    });
    expect(reset.status()).toBe(200);

    const page = await owner.newPage();
    await installOfflineFonts(page);
    page.on('pageerror', error => errors.push(error.name));
    await openNativeWorld(page, 'Home visitor', worldProofUrl(baseURL, identity.lng));
    await enterWorld(page);
    const open = page.getByRole('button', { name: homeLabel('open'), exact: true });
    await expect(open).toBeEnabled();
    await open.click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    const teal = page.getByRole('radio', { name: homeLabel('palettes', 'teal'), exact: true });
    await teal.focus();
    await page.keyboard.press('Space');
    await expect(teal).toBeChecked();
    const verified = page.waitForResponse(response => response.url().endsWith('/auth/me'));
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    expect((await verified).status()).toBe(200);
    await expect(dialog).toBeVisible();
    await expect(teal).toBeChecked();
    await page.screenshot({ path: info.outputPath('world-home-desktop.png') });
    await dialog.getByRole('button', { name: homeLabel('save'), exact: true }).click();
    await expect(dialog).not.toBeVisible();
    const saved: unknown = await (await owner.request.get('/api/v1/world/home')).json();
    expect(record(saved) && record(saved.preferences) && saved.preferences.palette).toBe('teal');
    expect(await (await other.request.get('/api/v1/world/home')).json()).toEqual(otherBefore);
    await open.click();
    await expect(teal).toBeChecked();
    await page.getByRole('radio', { name: homeLabel('palettes', 'sage'), exact: true }).check();
    await dialog.getByRole('button', { name: homeLabel('cancel'), exact: true }).click();
    expect(await (await owner.request.get('/api/v1/world/home')).json()).toEqual(saved);
    await open.click();
    const clay = page.getByRole('radio', { name: homeLabel('palettes', 'clay'), exact: true });
    await clay.check();
    const external = await owner.request.put('/api/v1/world/home', {
      data: {
        expected_revision: revision(saved),
        palette: 'amber',
      },
    });
    expect(external.status()).toBe(200);
    await dialog.getByRole('button', { name: homeLabel('save'), exact: true }).click();
    await expect(dialog.getByRole('alert')).toHaveText(homeLabel('conflict'));
    await expect(clay).toBeChecked();
    await dialog.getByRole('button', { name: homeLabel('reload'), exact: true }).click();
    await expect(dialog).not.toBeVisible();
    await expect(open).toBeEnabled();
    await open.click();
    await expect(
      page.getByRole('radio', { name: homeLabel('palettes', 'amber'), exact: true })
    ).toBeChecked();
    await expect(dialog.getByRole('radio')).toHaveCount(7);
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true
    );
    const cancel = dialog.getByRole('button', { name: homeLabel('cancel'), exact: true });
    await expect(cancel).toBeVisible();
    const bounds = await cancel.boundingBox();
    expect(bounds?.height).toBeGreaterThanOrEqual(44);
    expect((bounds?.y ?? 10000) + (bounds?.height ?? 0)).toBeLessThanOrEqual(844);
    const scan = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(
      scan.violations.map(value => ({ id: value.id, nodes: value.nodes.map(node => node.target) }))
    ).toEqual([]);
    await page.screenshot({ path: info.outputPath('world-home-mobile.png') });
    await page.setViewportSize({ width: 667, height: 375 });
    const palette = teal.locator('..');
    await palette.scrollIntoViewIfNeeded();
    const field = await palette.boundingBox();
    const actions = await cancel.boundingBox();
    expect(field?.height).toBeGreaterThanOrEqual(44);
    expect((field?.y ?? 10000) + (field?.height ?? 0)).toBeLessThanOrEqual(actions?.y ?? 0);
    await page.screenshot({ path: info.outputPath('world-home-landscape.png') });
    await page.keyboard.press('Escape');
    await expect(dialog).not.toBeVisible();
    await expect(page.locator('.world-hud-toggle')).toBeFocused();
    const malformed = await owner.request.put('/api/v1/world/home', {
      data: { expected_revision: 0, owner_id: 'do-not-reflect-home-fixture' },
    });
    expect(malformed.status()).toBe(422);
    expect(await malformed.text()).not.toContain('do-not-reflect-home-fixture');
    expect(malformed.headers()['cache-control']).toBe('no-store');
    await revealWorldControls(page);
    await page.getByRole('button', { name: sessionLabel('leave'), exact: true }).click();
    expect(errors).toEqual([]);
    expect(escaped).toEqual([]);
  } catch (error) {
    console.info('Native home before cleanup:', error instanceof Error ? error.message : 'unknown');
    const failedPage = active?.pages()[0];
    if (failedPage) await failedPage.screenshot({ path: info.outputPath('before-cleanup.png') });
    throw error;
  } finally {
    try {
      if (active && canReset) {
        const current: unknown = await (await active.request.get('/api/v1/world/home')).json();
        await active.request.put('/api/v1/world/home', {
          data: { expected_revision: revision(current), reset: true },
        });
        for (const page of active.pages()) {
          await page.keyboard.press('Escape');
          const dialogLeave = page
            .getByRole('dialog')
            .getByRole('button', { name: sessionLabel('leave'), exact: true });
          const leave = page.getByRole('button', { name: sessionLabel('leave'), exact: true });
          if (await dialogLeave.count()) await dialogLeave.click();
          else if (await leave.count()) {
            await revealWorldControls(page);
            await leave.last().click();
          }
        }
      }
    } finally {
      const closed = await Promise.allSettled(contexts.map(context => context.close()));
      expect(closed.filter(result => result.status === 'rejected')).toEqual([]);
    }
  }
});
