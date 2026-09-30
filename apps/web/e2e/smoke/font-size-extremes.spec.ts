/**
 * Interface text size — only the TEXT changes; panels keep their dimensions.
 *
 * The setting (Settings › Personalization › Font size) multiplies every font
 * size of the stylesheet by `--lia-text-scale` and leaves the root `rem` alone.
 * The first version scaled the root size instead: panels, the debug panel and
 * the settings shrank with the text, which the owner rejected (2026-09-29).
 * This spec is where that contract is measured:
 *
 *  1. the text follows the size (the body, a Tailwind `text-sm`, a `text-px-*`
 *     caption) while the chat panel, the dashboard header, the settings rail
 *     and the settings pane keep EXACTLY the boxes they have at the default;
 *  2. at the smallest and the largest size, the two densest control rows keep
 *     every control on screen and uncovered, at every width from the 320 px
 *     reflow floor to a desktop, and no page scrolls sideways;
 *  3. the section works end to end: A+ resizes the text, saves the size to the
 *     account, survives a reload (applied before paint), and a size chosen on
 *     another device reaches this one.
 *
 * The size is seeded the way a returning visitor has it — in localStorage for
 * the pre-paint script, and on the account — so the first paint is measured.
 */
import type { Page } from '@playwright/test';

import { test, expect, loadedChatRoutes, type MockRoute } from '../fixtures';
import { probeControls, waitForStableControls, type ControlRow } from './control-probe';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const FONT_SIZE_STORAGE_KEY = 'font-size';
const MIN_PX = 14;
const DEFAULT_PX = 16;
const MAX_PX = 20;

const SETTINGS_ROUTES: MockRoute[] = [
  { url: '**/api/v1/connectors', json: { connectors: [] } },
  { url: '**/api/v1/scheduled-actions**', json: { actions: [], total: 0 } },
  { url: '**/api/v1/usage/**', json: {} },
];

/** Seed the stored size before any page script, as a returning visitor has it. */
async function seedFontSize(page: Page, px: number): Promise<void> {
  await page.addInitScript(([key, value]) => window.localStorage.setItem(key, value), [
    FONT_SIZE_STORAGE_KEY,
    String(px),
  ] as const);
}

/** Computed font size, in px, of the first element matching the selector. */
async function fontSizeOf(page: Page, selector: string): Promise<number> {
  return page.evaluate(sel => {
    const el = document.querySelector(sel);
    if (!el) throw new Error(`no element for ${sel}`);
    return parseFloat(getComputedStyle(el).fontSize);
  }, selector);
}

/**
 * The size a `text-px-10` caption renders at, measured on a witness span added
 * for the occasion: every real caption on these pages also carries a
 * responsive size, which would measure the variant instead of the utility.
 */
async function pxCaptionSize(page: Page): Promise<number> {
  return page.evaluate(() => {
    const witness = document.createElement('span');
    witness.className = 'text-px-10';
    witness.textContent = 'x';
    document.body.appendChild(witness);
    const size = parseFloat(getComputedStyle(witness).fontSize);
    witness.remove();
    return size;
  });
}

/** The boxes that must not move: rounded to the pixel, keyed by what they are. */
/**
 * `box`: position and size, for panels whose height is fixed (the header, the
 * chat frame). `horizontal`: x and width only, for panels that hold running
 * text — larger text makes a text block taller, never a panel narrower.
 */
async function panelBoxes(
  page: Page,
  selectors: Record<string, string>,
  axes: 'box' | 'horizontal'
) {
  return page.evaluate(
    ([sels, mode]) => {
      const boxes: Record<string, string> = {};
      for (const [name, sel] of Object.entries(sels)) {
        const el = document.querySelector(sel);
        if (!el) throw new Error(`no panel for ${name} (${sel})`);
        const r = el.getBoundingClientRect();
        boxes[name] =
          mode === 'box'
            ? `${Math.round(r.x)},${Math.round(r.y)} ${Math.round(r.width)}×${Math.round(r.height)}`
            : `x=${Math.round(r.x)} w=${Math.round(r.width)}`;
      }
      return boxes;
    },
    [selectors, axes] as const
  );
}

async function openFontSizeSection(page: Page, lng: string): Promise<void> {
  await page.goto(`/${lng}/dashboard/settings?section=font-size`);
  await expect(page.locator('#settings-section-font-size')).toBeVisible({ timeout: 20_000 });
}

const CHAT_PANELS = {
  header: 'header',
  chatShell: '[class*="calc(100vh"]',
  chatPanel: '[class*="calc(100vh"] > div',
};
const SETTINGS_PANELS = {
  header: 'header',
  rail: 'aside',
  pane: '#settings-section-font-size',
};

test.describe('text size — the text follows, the panels do not', () => {
  for (const size of [MIN_PX, MAX_PX] as const) {
    test(`chat and settings keep their panels at ${size} px`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await mockApi([...loadedChatRoutes(), ...SETTINGS_ROUTES]);

      // The reference: the same pages at the default size.
      await authenticate({ language: 'fr', font_size: DEFAULT_PX });
      await page.goto('/fr/dashboard/chat');
      await page.locator('textarea').first().waitFor({ state: 'visible' });
      await awaitStyledPage(page, 'chat @ default');
      const chatAtDefault = await panelBoxes(page, CHAT_PANELS, 'box');
      await openFontSizeSection(page, 'fr');
      await awaitStyledPage(page, 'settings @ default');
      const settingsAtDefault = await panelBoxes(page, SETTINGS_PANELS, 'horizontal');

      await authenticate({ language: 'fr', font_size: size });
      await seedFontSize(page, size);
      await page.goto('/fr/dashboard/chat');
      await page.locator('textarea').first().waitFor({ state: 'visible' });
      await awaitStyledPage(page, `chat @ ${size}px`);
      expect(await panelBoxes(page, CHAT_PANELS, 'box')).toEqual(chatAtDefault);

      // …while the text did change, whatever wrote its size: the body, the
      // message text (Tailwind `text-sm` at this width) and a px caption.
      expect(await fontSizeOf(page, 'body')).toBeCloseTo(size, 2);
      expect(await fontSizeOf(page, '.markdown-content')).toBeCloseTo(size * 0.875, 2);
      expect(await pxCaptionSize(page)).toBeCloseTo((10 * size) / DEFAULT_PX, 2);

      await openFontSizeSection(page, 'fr');
      await awaitStyledPage(page, `settings @ ${size}px`);
      expect(await panelBoxes(page, SETTINGS_PANELS, 'horizontal')).toEqual(settingsAtDefault);
      expect(await fontSizeOf(page, 'span.tabular-nums.text-sm')).toBeCloseTo(size * 0.875, 2);
    });
  }
});

test.describe('text size — the densest rows hold at both ends', () => {
  // Both edges of every band: a breakpoint switches the layout on the SCREEN
  // width, so a width just above one is where larger text is tightest.
  const WIDTHS = [320, 390, 430, 640, 768, 880, 960, 1024, 1100, 1280, 1440] as const;
  const CASES = [
    { size: MIN_PX, lng: 'fr' },
    { size: MAX_PX, lng: 'fr' },
    // German carries the longest labels: the first to break when text grows.
    { size: MAX_PX, lng: 'de' },
  ] as const;

  for (const { size, lng } of CASES) {
    test(`headers and chat hold at ${size} px @ ${lng}`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await authenticate({ language: lng, font_size: size });
      await mockApi(loadedChatRoutes());
      await seedFontSize(page, size);
      await page.goto(`/${lng}/dashboard/chat`);
      await page.locator('textarea').first().waitFor({ state: 'visible' });
      await awaitStyledPage(page, `/dashboard/chat @ ${size}px`);

      for (const width of WIDTHS) {
        await page.setViewportSize({ width, height: 800 });
        await page.waitForFunction(w => document.documentElement.clientWidth === w, width);

        for (const row of ['dashboard-header', 'chat-header'] as ControlRow[]) {
          await waitForStableControls(page, row);
          const { clipped, overlaps } = await probeControls(page, row);
          const where = `${row} ${lng} @ ${width}px, text ${size}px`;
          // Soft: one run reports every width that breaks, not only the first.
          expect
            .soft(
              clipped,
              `${where} — controls off-screen: ` +
                clipped.map(c => `${c.name} (+${c.overflowPx}px)`).join(', ')
            )
            .toEqual([]);
          expect.soft(overlaps, `${where} — controls overlap: ${overlaps.join(' | ')}`).toEqual([]);
        }
        await expectNoOverflow(page, `chat @ ${width}px, text ${size}px (${lng})`);
      }
    });
  }

  for (const size of [MIN_PX, MAX_PX] as const) {
    // The tablet band too: just above `mobile` the layout is the desktop one.
    for (const width of [320, 880, 1280] as const) {
      test(`the font size pane holds at ${size} px on ${width} px`, async ({
        page,
        authenticate,
        mockApi,
      }) => {
        await authenticate({ language: 'fr', font_size: size });
        await mockApi(SETTINGS_ROUTES);
        await seedFontSize(page, size);
        await page.setViewportSize({ width, height: 800 });
        await openFontSizeSection(page, 'fr');
        await awaitStyledPage(page, `settings font-size @ ${width}px, text ${size}px`);

        // Every control of the section stays operable at its own extreme; the
        // bound is announced, never `disabled` (a focused button would blur).
        const increase = page.getByRole('button', { name: 'Agrandir la taille du texte' });
        const decrease = page.getByRole('button', { name: 'Réduire la taille du texte' });
        await expect(increase).toBeVisible();
        await expect(decrease).toBeVisible();
        await expect(size === MAX_PX ? increase : decrease).toHaveAttribute(
          'aria-disabled',
          'true'
        );
        await expect(page.getByRole('slider', { name: 'Taille du texte' })).toBeVisible();

        await expectNoOverflow(page, `settings font-size @ ${width}px, text ${size}px`);
      });
    }
  }
});

test('A+ resizes the text, saves the size and survives a reload', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const user = await authenticate({ language: 'fr' });
  const saved: Array<{ font_size: number }> = [];
  // The account echoes what was saved, as the real one does: a stale 16 would
  // (rightly) be applied back by FontPreferencesSync after the reload.
  const account = () => ({ ...user, font_size: saved.at(-1)?.font_size ?? user.font_size });
  await mockApi([
    ...SETTINGS_ROUTES,
    { url: '**/api/v1/auth/me', handler: route => route.fulfill({ json: account() }) },
    {
      url: `**/api/v1/users/${user.id}`,
      method: 'PATCH',
      handler: async route => {
        saved.push(route.request().postDataJSON());
        await route.fulfill({ status: 200, json: account() });
      },
    },
  ]);
  await page.setViewportSize({ width: 1280, height: 800 });
  await openFontSizeSection(page, 'fr');
  expect(await fontSizeOf(page, 'body')).toBe(DEFAULT_PX);

  await page.getByRole('button', { name: 'Agrandir la taille du texte' }).click();

  await expect.poll(() => fontSizeOf(page, 'body')).toBe(17);
  await expect.poll(() => saved).toEqual([{ font_size: 17 }]);
  await expect(page.getByRole('slider', { name: 'Taille du texte' })).toHaveAttribute(
    'aria-valuenow',
    '17'
  );

  await page.reload();
  await page.waitForLoadState('domcontentloaded');
  // Applied by the pre-paint script, from the device's own copy.
  expect(
    await page.evaluate(() => document.documentElement.style.getPropertyValue('--lia-text-scale'))
  ).toBe('1.0625');
  expect(await fontSizeOf(page, 'body')).toBe(17);
});

test("the account's size reaches a device that never chose one", async ({
  page,
  authenticate,
  mockApi,
}) => {
  // Chosen on another device: nothing stored here, the account holds 18 px.
  await authenticate({ language: 'fr', font_size: 18 });
  await mockApi(SETTINGS_ROUTES);
  await page.setViewportSize({ width: 1280, height: 800 });
  await openFontSizeSection(page, 'fr');

  await expect.poll(() => fontSizeOf(page, 'body')).toBe(18);
  expect(await page.evaluate(key => window.localStorage.getItem(key), FONT_SIZE_STORAGE_KEY)).toBe(
    '18'
  );
});
