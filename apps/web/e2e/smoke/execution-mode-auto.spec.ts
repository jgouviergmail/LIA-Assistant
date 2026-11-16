/**
 * The automatic execution mode in a real browser (ADR-390): the chat header's
 * three-choice menu, and the badge naming the engine under an automatic answer,
 * on a 320 px phone and a 1280 px desktop.
 *
 * Hermetic: the account, the conversation and the preference endpoint are
 * mocked; everything else dies on the 501 catch-all. What only a laid-out page
 * proves:
 *
 * 1. **The badge never leaves a phone's screen.** Under an answer older than a
 *    week the meta line carries the long date, in Spanish the longest one; with
 *    the badge it is wider than a 320 px bubble, and the badge must drop under
 *    the date whole instead of pushing the page sideways. On a desktop it
 *    shares the time's line, after a bar: « time | ReAct ».
 * 2. **The badge stands level with the time**, on a phone and a desktop: its
 *    word centred on the time's and the line no taller than without it — the
 *    owner saw the time sit lower once the badge was there.
 * 3. **The menu is the header's control at both widths**: it opens inside the
 *    screen, offers the three modes with the chosen one checked, passes an axe
 *    scan, and a choice sends the PATCH, reads the account back and says so.
 */
import type { Locator, Page } from '@playwright/test';

import { test, expect, loadedChatRoutes, waitForHydration, type MockRoute } from '../fixtures';
import { scanPage } from '../a11y/scan';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const PHONE = { width: 320, height: 720 };
const DESKTOP = { width: 1280, height: 800 };
const DAY_MS = 86_400_000;

/** An automatic answer; ten days old by default, so the meta line shows the long date. */
function automaticAnswer(engine: 'pipeline' | 'react', daysAgo: number): Record<string, unknown> {
  return {
    id: '00000000-0000-4000-8000-00000000e390',
    role: 'assistant',
    content: '<p>Voici le plan de la semaine.</p>',
    message_metadata: { execution_engine: engine },
    created_at: new Date(Date.now() - daysAgo * DAY_MS).toISOString(),
  };
}

function conversation(engine: 'pipeline' | 'react', daysAgo = 10): MockRoute {
  return {
    url: '**/api/v1/conversations/me/messages*',
    json: {
      messages: [automaticAnswer(engine, daysAgo)],
      conversation_id: '00000000-0000-4000-8000-0000000000ff',
      total_count: 1,
      has_more: false,
      next_cursor: null,
    },
  };
}

/** The meta line under the bubble: the element holding the time as its own text. */
function metaLine(page: Page): Locator {
  return page
    .locator('.message-bubble-assistant')
    .locator('xpath=following-sibling::span[1]')
    .first();
}

async function box(locator: Locator) {
  const found = await locator.boundingBox();
  if (!found) throw new Error('Expected a laid-out element');
  return found;
}

/**
 * Where the badge's word stands against the time, and what the badge does to
 * the line: the owner saw the time sit lower once the badge was there.
 * `offset` is the word's vertical centre minus the time's; `growth` is the
 * line's height with the mark minus its height without it.
 */
async function alignment(page: Page): Promise<{ offset: number; growth: number }> {
  return page.evaluate(() => {
    const meta = document.querySelector('.message-bubble-assistant')?.nextElementSibling;
    if (!(meta instanceof HTMLElement)) throw new Error('Expected the meta line');
    const timeNode = Array.from(meta.childNodes).find(
      node => node.nodeType === Node.TEXT_NODE && (node.textContent ?? '').trim()
    );
    const badge = meta.querySelector('[data-execution-engine]');
    const word = badge?.querySelector(':scope > span[aria-hidden="true"]');
    const mark = badge?.parentElement?.parentElement;
    if (!timeNode || !(word instanceof HTMLElement) || !(mark instanceof HTMLElement)) {
      throw new Error('Expected the time and the engine mark');
    }
    const time = document.createRange();
    time.selectNodeContents(timeNode);
    const centre = (rect: DOMRect) => (rect.top + rect.bottom) / 2;
    const offset = centre(word.getBoundingClientRect()) - centre(time.getBoundingClientRect());
    const withMark = meta.getBoundingClientRect().height;
    mark.style.display = 'none';
    const bare = meta.getBoundingClientRect().height;
    mark.style.display = '';
    return { offset, growth: withMark - bare };
  });
}

test.describe('the engine badge under an automatic answer', () => {
  test('drops under a long date on a 320 px phone instead of overflowing', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize(PHONE);
    await authenticate({ language: 'es' });
    await mockApi([...loadedChatRoutes(), conversation('pipeline')]);
    await page.goto('/es/dashboard/chat');
    await waitForHydration(page, 'textarea');
    await awaitStyledPage(page, 'phone badge');

    const badge = page.locator('[data-execution-engine="pipeline"]');
    // The word is what a person sees; the whole sentence is the hover title and
    // what a screen reader hears instead of the bare word.
    await expect(badge.getByText('Pipeline', { exact: true })).toBeVisible();
    await expect(badge).toContainText('Modo automático: respuesta producida por un plan Pipeline');
    await expect(badge).toHaveAttribute(
      'title',
      'Modo automático: respuesta producida por un plan Pipeline'
    );

    const mark = await box(badge);
    expect(mark.x).toBeGreaterThanOrEqual(0);
    expect(mark.x + mark.width).toBeLessThanOrEqual(PHONE.width);
    // The line wrapped: the badge sits under the date, not beside it.
    const line = await box(metaLine(page));
    expect(mark.y).toBeGreaterThan(line.y + 4);
    await expectNoOverflow(page, 'phone badge');
  });

  test('shares the time’s line on a desktop', async ({ page, authenticate, mockApi }) => {
    await page.setViewportSize(DESKTOP);
    await authenticate();
    await mockApi([...loadedChatRoutes(), conversation('react')]);
    await page.goto('/en/dashboard/chat');
    await waitForHydration(page, 'textarea');
    await awaitStyledPage(page, 'desktop badge');

    const badge = page.locator('[data-execution-engine="react"]');
    await expect(badge.getByText('ReAct', { exact: true })).toBeVisible();
    // « time | ReAct »: the bar the owner asked for, after the time.
    await expect(metaLine(page)).toContainText('| ReAct');
    const { offset, growth } = await alignment(page);
    // Level with the time, and the line no taller than on any other bubble.
    expect(Math.abs(offset)).toBeLessThanOrEqual(1);
    expect(growth).toBeLessThanOrEqual(1);
    await expectNoOverflow(page, 'desktop badge');
  });

  test('stands level with the time on a phone', async ({ page, authenticate, mockApi }) => {
    await page.setViewportSize({ width: 390, height: 720 });
    await authenticate({ language: 'fr' });
    await mockApi([...loadedChatRoutes(), conversation('react', 0)]);
    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page, 'textarea');
    await awaitStyledPage(page, 'phone level');

    await expect(page.locator('[data-execution-engine="react"]')).toBeVisible();
    await expect(metaLine(page)).toContainText('| ReAct');
    const { offset, growth } = await alignment(page);
    expect(Math.abs(offset)).toBeLessThanOrEqual(1);
    expect(growth).toBeLessThanOrEqual(1);
    await expectNoOverflow(page, 'phone level');
  });
});

test.describe('the header menu', () => {
  for (const viewport of [PHONE, DESKTOP]) {
    test(`offers the three modes and saves one at ${viewport.width} px`, async ({
      page,
      authenticate,
      mockApi,
    }, testInfo) => {
      await page.setViewportSize(viewport);
      const user = await authenticate({ execution_mode: 'pipeline' });
      let stored = 'pipeline';
      const patches: unknown[] = [];
      await mockApi([
        ...loadedChatRoutes(),
        {
          url: '**/api/v1/auth/me',
          handler: route => route.fulfill({ json: { ...user, execution_mode: stored } }),
        },
        {
          url: '**/api/v1/auth/me/execution-mode-preference',
          method: 'PATCH',
          handler: async route => {
            const body: unknown = route.request().postDataJSON();
            patches.push(body);
            stored = 'auto';
            await route.fulfill({
              json: { execution_mode: stored, auto_resolution: 'decided' },
            });
          },
        },
      ]);
      await page.goto('/en/dashboard/chat');
      await waitForHydration(page, 'textarea');
      await awaitStyledPage(page, `menu ${viewport.width}`);

      const header = page.locator('header');
      await header.getByRole('button', { name: 'Execution: Pipeline mode', exact: true }).click();
      const menu = page.getByRole('menu');
      await expect(menu).toBeVisible();
      const items = menu.getByRole('menuitemradio');
      await expect(items).toHaveCount(3);
      await expect(items.nth(0)).toHaveAttribute('aria-checked', 'true');
      const open = await box(menu);
      expect(open.x).toBeGreaterThanOrEqual(0);
      expect(open.x + open.width).toBeLessThanOrEqual(viewport.width);
      await scanPage(page, testInfo, `execution mode menu ${viewport.width}`, '[role="menu"]');

      await items.nth(2).click();

      await expect.poll(() => patches).toEqual([{ execution_mode: 'auto' }]);
      await expect(
        header.getByRole('button', { name: 'Execution: Automatic mode', exact: true })
      ).toBeVisible();
      await expect(page.getByText('Automatic mode enabled')).toBeVisible();
      await expectNoOverflow(page, `menu ${viewport.width}`);
    });
  }
});
