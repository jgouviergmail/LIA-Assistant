/** Replay the iOS keyboard coordinate contract; compare actual painted browser bounds. */
import type { Locator, Page } from '@playwright/test';
import { test, expect, loadedChatRoutes, waitForHydration } from '../fixtures';
import { selectionRoutes, dictationEnabled } from '../fixtures/selection-assist';
import fr from '../../locales/fr/translation.json';

test.use({ hasTouch: true, viewport: { width: 390, height: 844 } });

async function panKeyboard(field: Locator) {
  return field.evaluate(element => {
    const nativeRect = Element.prototype.getBoundingClientRect;
    const source = nativeRect.call(element);
    const viewport = Object.assign(new EventTarget(), {
      offsetLeft: 0,
      offsetTop: source.top - 240,
      width: window.innerWidth,
      height: 360,
      scale: 1,
      pageLeft: 0,
      pageTop: window.scrollY + source.top - 240,
    });
    Object.defineProperty(window, 'visualViewport', { configurable: true, value: viewport });
    // Only the geometry boundary under test is replayed. The app, focus, native
    // fields and fixed-position painting remain real. locator.boundingBox()
    // reads the engine's painted quads independently of this page-world getter.
    Element.prototype.getBoundingClientRect = function (this: Element) {
      const rect = nativeRect.call(this);
      if (this !== element && !this.matches('[data-selection-assist-ui]')) return rect;
      return new DOMRect(
        rect.left - viewport.offsetLeft,
        rect.top - viewport.offsetTop,
        rect.width,
        rect.height
      );
    };
    viewport.dispatchEvent(new Event('resize'));
    viewport.dispatchEvent(new Event('scroll'));
    return { top: viewport.offsetTop, bottom: viewport.offsetTop + viewport.height };
  });
}

async function expectBeside(
  field: Locator,
  overlay: Locator,
  viewport: { top: number; bottom: number }
) {
  await expect(overlay).toBeVisible();
  await expect
    .poll(async () => {
      const source = await field.boundingBox();
      const panel = await overlay.boundingBox();
      if (!source || !panel) return false;
      return (
        Math.abs(source.y - (panel.y + panel.height) - 8) <= 1 &&
        panel.y >= viewport.top &&
        panel.y + panel.height <= viewport.bottom &&
        panel.x >= 0 &&
        panel.x + panel.width <= 390
      );
    })
    .toBe(true);
}

async function closeKeyboard(page: Page) {
  await page.evaluate(() => {
    const viewport = window.visualViewport;
    if (!viewport) throw new Error('Missing keyboard fixture');
    Object.assign(viewport, { offsetTop: 0, height: window.innerHeight, pageTop: window.scrollY });
    viewport.dispatchEvent(new Event('resize'));
    viewport.dispatchEvent(new Event('scroll'));
  });
}

for (const surface of ['chat', 'mail'] as const) {
  for (const mode of ['caret', 'selection'] as const) {
    test(`${surface} ${mode} stays above its bottom field across a keyboard pan`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await authenticate({ language: 'fr' });
      await mockApi([...loadedChatRoutes(), ...selectionRoutes, dictationEnabled]);
      await mockApi([
        {
          url: '**/api/v1/tool-assists/text/selection/stream',
          method: 'POST',
          handler: route =>
            route.fulfill({
              contentType: 'text/event-stream',
              body: `data: ${JSON.stringify({ result: { proposal: { kind: 'text', text: 'Texte corrigé' }, usage: null } })}\n\n`,
            }),
        },
      ]);
      const tickets: string[] = [];
      page.on('request', request => {
        if (new URL(request.url()).pathname.endsWith('/voice/ticket')) tickets.push(request.url());
      });
      await page.goto(surface === 'chat' ? '/fr/dashboard/chat' : '/fr/dashboard/tools/mail');
      await waitForHydration(page, 'main');
      if (surface === 'mail')
        await page.getByRole('button', { name: 'Nouvel email', exact: true }).first().click();
      const field =
        surface === 'chat'
          ? page.locator('[data-chat-composer]')
          : page
              .getByRole('dialog', { name: 'Nouvel email', exact: true })
              .getByRole('textbox', { name: 'Message', exact: true });
      await expect(field).toBeEnabled();
      // ChatInput owns an existing idle voice prewarm. Opening or moving this
      // separate control must not add another request on either surface.
      await expect.poll(() => tickets.length).toBe(surface === 'chat' ? 1 : 0);
      const initialTickets = [...tickets];
      await field.fill('Un passage à améliorer.');
      await field.press(mode === 'caret' ? 'End' : 'ControlOrMeta+a');
      const toolbar = page.getByRole('toolbar', {
        name: mode === 'caret' ? fr.selectionAssist.voice.dictate : fr.selectionAssist.label,
        exact: true,
      });
      await expectBeside(field, toolbar, { top: 0, bottom: 844 });
      const viewport = await panKeyboard(field);
      expect(viewport.top).toBeGreaterThan(0);
      await expectBeside(field, toolbar, viewport);
      if (mode === 'selection') {
        await toolbar.getByRole('button', { name: 'Corriger', exact: true }).click();
        const answer = page.getByRole('dialog', { name: 'Corriger', exact: true });
        await expect(answer.getByText('Texte corrigé', { exact: true })).toBeVisible();
        await expectBeside(field, answer, viewport);
        await closeKeyboard(page);
        await expectBeside(field, answer, { top: 0, bottom: 844 });
      } else {
        await closeKeyboard(page);
        await expectBeside(field, toolbar, { top: 0, bottom: 844 });
      }
      await expect(field).toHaveValue('Un passage à améliorer.');
      expect(tickets).toEqual(initialTickets);
    });
  }
}
