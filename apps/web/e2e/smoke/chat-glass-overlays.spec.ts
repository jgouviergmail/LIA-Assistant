/** Real portals and Sonner paint, with hermetic API/clipboard and no destructive action. */
import AxeBuilder from '@axe-core/playwright';
import type { Locator, Page } from '@playwright/test';
import { test, expect, loadedChatRoutes, waitForHydration } from '../fixtures';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

async function applyTheme(page: Page, theme: string) {
  await page.evaluate(value => {
    document.documentElement.classList.toggle('dark', value !== 'light');
    document.documentElement.toggleAttribute('data-oled', value === 'oled');
  }, theme);
}

async function expectMaterial(surface: Locator, width: number) {
  await expect(surface).toBeVisible();
  const material = await surface.evaluate(node => {
    const style = getComputedStyle(node);
    const box = node.getBoundingClientRect();
    return {
      blur: style.backdropFilter || style.getPropertyValue('-webkit-backdrop-filter'),
      reflection: style.backgroundImage,
      background: style.backgroundColor,
      x: box.x,
      right: box.right,
    };
  });
  expect(material.blur).toContain('blur(');
  expect(material.reflection).not.toBe('none');
  expect(material.background).not.toBe('rgba(0, 0, 0, 0)');
  expect(material.x).toBeGreaterThanOrEqual(0);
  expect(material.right).toBeLessThanOrEqual(width + 1);
}

async function expectAccessible(page: Page, selector: string) {
  const result = await new AxeBuilder({ page })
    .include(selector)
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  expect(result.violations).toEqual([]);
}

// The glass is drawn only where nobody asked for less transparency, and
// Chromium reads that preference from the HOST: on a Windows workstation with
// transparency effects off, every surface is rightly opaque and the baseline
// assertions measured the machine instead of the product (measured 2026-10-04).
// The baseline is pinned; the preference test below asks for `reduce` itself.
test.beforeEach(async ({ page, browserName }) => {
  if (browserName !== 'chromium') return;
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Emulation.setEmulatedMedia', {
    features: [{ name: 'prefers-reduced-transparency', value: 'no-preference' }],
  });
});

for (const sample of [
  { width: 1280, theme: 'light' },
  { width: 390, theme: 'dark' },
  { width: 320, theme: 'oled' },
]) {
  test(`glass dialogs, menu and notifications ${sample.width} ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: sample.width, height: 900 });
    await page.addInitScript(() => {
      const write = () =>
        document.documentElement.dataset.clipboardFailure
          ? Promise.reject(new Error('LOCAL_CLIPBOARD_REFUSAL'))
          : Promise.resolve();
      Object.defineProperty(navigator, 'clipboard', { value: { write, writeText: write } });
    });
    await authenticate();
    await mockApi([
      ...loadedChatRoutes(),
      { url: '**/api/v1/rag-spaces/documents*', json: { items: [], total: 0 } },
    ]);
    const writes: string[] = [];
    page.on('request', request => {
      const shellOnly = ['/api/v1/habits/presence', '/api/v1/voice/ticket'];
      if (
        request.method() !== 'GET' &&
        request.url().includes('/api/v1/') &&
        !shellOnly.includes(new URL(request.url()).pathname)
      )
        writes.push(`${request.method()} ${request.url()}`);
    });
    await page.goto('/en/dashboard/chat');
    await waitForHydration(page, 'textarea');
    await awaitStyledPage(page, 'glass overlays');
    await applyTheme(page, sample.theme);
    // The Next development portal is unrelated to the product's touch geometry.
    await page.addStyleTag({ content: 'nextjs-portal { display: none !important; }' });

    const reset = page.getByRole('button', { name: 'Delete', exact: true });
    await reset.focus();
    await page.keyboard.press('Enter');
    const confirmation = page.getByRole('alertdialog');
    await expectMaterial(confirmation, sample.width);
    await expect(confirmation).toHaveAccessibleName('Delete this conversation?');
    await expectAccessible(page, '[role=alertdialog]');
    await page.screenshot({
      path: test.info().outputPath(`confirmation-${sample.theme}.png`),
    });
    await confirmation.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(reset).toBeFocused();

    const attachment = page.getByRole('button', { name: 'Attach a file', exact: true });
    await attachment.focus();
    await page.keyboard.press('Enter');
    const menu = page.getByRole('menu');
    await expectMaterial(menu, sample.width);
    for (const item of await menu.getByRole('menuitem').all()) {
      expect((await item.boundingBox())?.height).toBeGreaterThanOrEqual(44);
      const alignment = await item.evaluate(node => {
        const svg = node.querySelector('svg')?.getBoundingClientRect();
        const box = node.getBoundingClientRect();
        return svg ? Math.abs(svg.y + svg.height / 2 - box.y - box.height / 2) : 0;
      });
      expect(alignment).toBeLessThanOrEqual(1);
    }
    await page.keyboard.press('Escape');
    await expect(attachment).toBeFocused();
    await attachment.click();
    await page.getByRole('menuitem', { name: 'Document from a knowledge space' }).click();
    const dialog = page.getByRole('dialog', {
      name: 'Attach a document from your knowledge spaces',
    });
    await expectMaterial(dialog, sample.width);
    const close = dialog.getByRole('button', { name: 'Close', exact: true });
    const closeBox = await close.boundingBox();
    expect(closeBox?.width).toBeGreaterThanOrEqual(44);
    expect(closeBox?.height).toBeGreaterThanOrEqual(44);
    const title = await dialog.getByRole('heading').boundingBox();
    expect((title?.x ?? 0) + (title?.width ?? 0)).toBeLessThanOrEqual(closeBox?.x ?? 0);
    await expectAccessible(page, '[role=dialog]');
    await dialog.screenshot({ path: test.info().outputPath(`dialog-${sample.theme}.png`) });
    await dialog.getByRole('searchbox', { name: 'Search by name' }).focus();
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(attachment).toBeFocused();

    const copy = page.getByRole('button', { name: 'Copy message', exact: true });
    await copy.click();
    const success = page.locator('[data-sonner-toast][data-type=success]');
    await expectMaterial(success, sample.width);
    await success.hover();
    await expectAccessible(page, '[data-sonner-toast]');
    await success.screenshot({ path: test.info().outputPath(`notification-${sample.theme}.png`) });
    const notificationClose = success.getByRole('button', { name: 'Close', exact: true });
    expect((await notificationClose.boundingBox())?.width).toBeGreaterThanOrEqual(44);
    await notificationClose.focus();
    await page.keyboard.press('Enter');
    await expect(success).toHaveCount(0);
    await page.evaluate(() => (document.documentElement.dataset.clipboardFailure = 'true'));
    await copy.click();
    const error = page.locator('[data-sonner-toast][data-type=error]');
    await expectMaterial(error, sample.width);
    await error.hover();
    await expectAccessible(page, '[data-sonner-toast]');
    await expectNoOverflow(page, 'glass overlays and notifications');
    await page.mouse.move(0, 550);
    await expect(error).toHaveCount(0, { timeout: 8500 });
    expect(writes).toEqual([]);
  });

  test(`glass select with available-height scroll ${sample.width} ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: sample.width, height: 580 });
    await authenticate();
    await mockApi([
      {
        url: '**/api/v1/config',
        json: {
          sse: { heartbeat_interval_seconds: 30 },
          rate_limits: { enabled: false, per_minute: 60, burst: 10 },
          i18n: { supported_languages: ['en'], default_language: 'en' },
          features: { meetings_enabled: true },
          api_version: 'v1',
        },
      },
      {
        url: '**/api/v1/meetings/preferences',
        json: {
          stt_engine: 'auto',
          language: 'auto',
          auto_email: false,
          keep_audio_hours: 0,
          keep_audio_hours_max: 72,
          default_template_ref: null,
        },
      },
      { url: '**/api/v1/meetings/templates', json: { items: [], max_user_templates: 25 } },
      { url: '**/api/v1/meetings?*', json: { items: [], total: 0, limit: 5, offset: 0 } },
    ]);
    await page.goto('/en/dashboard/settings?section=meetings');
    const select = page.locator('#meeting-language');
    await expect(select).toBeVisible();
    await awaitStyledPage(page, 'glass select');
    await applyTheme(page, sample.theme);
    await select.scrollIntoViewIfNeeded();
    await select.focus();
    await page.keyboard.press('ArrowDown');
    const list = page.getByRole('listbox');
    await expectMaterial(list, sample.width);
    // The list is still being placed when the key press returns: measured at
    // y = -650 on a slower host while the failure screenshot showed it on
    // screen. The geometry is asserted once it settles, not on whichever frame
    // the measurement happened to land on.
    await expect.poll(async () => (await list.boundingBox())?.y ?? -1).toBeGreaterThanOrEqual(0);
    const box = await list.boundingBox();
    expect(box?.y).toBeGreaterThanOrEqual(0);
    expect((box?.y ?? 0) + (box?.height ?? 0)).toBeLessThanOrEqual(581);
    await page.keyboard.press('End');
    const last = list.getByRole('option').last();
    await expect(last).toBeVisible();
    expect((await last.boundingBox())?.height).toBeGreaterThanOrEqual(44);
    await expectAccessible(page, '[role=listbox]');
    await list.screenshot({ path: test.info().outputPath(`select-${sample.theme}.png`) });
    await page.keyboard.press('Escape');
    await expect(select).toBeFocused();
    await expect(list).toHaveCount(0);
  });
}

test('glass tooltip and system accessibility preferences', async ({
  page,
  authenticate,
  mockApi,
  browserName,
}) => {
  await authenticate();
  await mockApi([
    ...loadedChatRoutes(),
    {
      url: '**/api/v1/config',
      json: {
        sse: { heartbeat_interval_seconds: 30 },
        rate_limits: { enabled: false, per_minute: 60, burst: 10 },
        i18n: { supported_languages: ['en'], default_language: 'en' },
        features: { attachments_enabled: true, rag_spaces_enabled: false },
        api_version: 'v1',
      },
    },
  ]);
  await page.goto('/en/dashboard/chat');
  await waitForHydration(page, 'textarea');
  await awaitStyledPage(page, 'glass preferences');
  const copy = page.getByRole('button', { name: 'Copy message', exact: true });
  await copy.hover();
  await copy.focus();
  const tooltip = page.getByRole('tooltip').and(page.locator('.lia-overlay-surface'));
  await expectMaterial(tooltip, 1280);
  expect(await tooltip.evaluate(node => getComputedStyle(node).animationName)).toBe('none');
  await expectAccessible(page, '.lia-overlay-surface');
  await page.keyboard.press('Escape');
  await expect(copy).toBeFocused();
  if (browserName === 'chromium') {
    const cdp = await page.context().newCDPSession(page);
    await cdp.send('Emulation.setEmulatedMedia', {
      features: [
        { name: 'prefers-reduced-transparency', value: 'reduce' },
        { name: 'prefers-reduced-motion', value: 'reduce' },
      ],
    });
    expect(
      await page.evaluate(() => matchMedia('(prefers-reduced-transparency: reduce)').matches)
    ).toBe(true);
    await page.mouse.move(0, 550);
    await copy.evaluate((node: HTMLElement) => node.blur());
    await copy.hover();
    await copy.focus();
    await expect(tooltip).toBeVisible();
    expect(await tooltip.evaluate(node => getComputedStyle(node).backdropFilter)).toBe('none');
    await cdp.detach();
  }
  await page.emulateMedia({ forcedColors: 'active', reducedMotion: 'reduce' });
  if (await page.evaluate(() => matchMedia('(forced-colors: active)').matches)) {
    await page.mouse.move(0, 550);
    await copy.evaluate((node: HTMLElement) => node.blur());
    await copy.hover();
    await copy.focus();
    await expect(tooltip).toBeVisible();
    expect(await tooltip.evaluate(node => getComputedStyle(node).backdropFilter)).toBe('none');
    expect(await tooltip.evaluate(node => getComputedStyle(node).boxShadow)).toBe('none');
  }
});
