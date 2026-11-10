/** Caret dictation and native touch selection recovery; no provider or record writes. */
import AxeBuilder from '@axe-core/playwright';
import { test, expect, waitForHydration, loadedChatRoutes } from '../fixtures';
import {
  selectionRoutes,
  dictationEnabled as enabled,
  undoNativeEdit,
  beginNativeTouchSelection,
  endNativeTouchSelection,
} from '../fixtures/selection-assist';
import en from '../../locales/en/translation.json';
import fr from '../../locales/fr/translation.json';

for (const lng of ['en', 'fr'] as const) {
  test(`caret dictation is compact, translated and closes with focus (${lng})`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const words = lng === 'fr' ? fr : en;
    const compose = lng === 'fr' ? 'Nouvel email' : 'New email';
    await page.setViewportSize({ width: 320, height: 720 });
    await authenticate({ language: lng });
    await mockApi([...selectionRoutes, enabled]);
    const tickets: string[] = [];
    page.on('request', request => {
      if (new URL(request.url()).pathname.endsWith('/voice/ticket')) tickets.push(request.url());
    });
    await page.goto(`/${lng}/dashboard/tools/mail`);
    await waitForHydration(page, 'main');
    await page.getByRole('button', { name: compose, exact: true }).first().click();
    const form = page.getByRole('dialog', { name: compose, exact: true });
    const subject = form.getByRole('textbox', {
      name: lng === 'fr' ? 'Objet' : 'Subject',
      exact: true,
    });
    const caret = page.getByRole('toolbar', {
      name: words.selectionAssist.voice.dictate,
      exact: true,
    });
    for (const kind of ['subject', 'plain', 'rich']) {
      if (kind === 'rich')
        await form
          .getByRole('button', { name: lng === 'fr' ? 'Mise en forme' : 'Formatting', exact: true })
          .click();
      const field =
        kind === 'subject' ? subject : form.getByRole('textbox', { name: 'Message', exact: true });
      await field.click();
      await expect(caret).toBeVisible();
      await expect(field).toBeFocused();
      expect((await caret.boundingBox())?.width).toBeLessThanOrEqual(180);
      await expect(caret.getByRole('button')).toHaveCount(2);
      expect(tickets).toEqual([]);
      expect(
        (await new AxeBuilder({ page }).include('[data-selection-assist-ui]').analyze()).violations
      ).toEqual([]);
      await field.press('Alt+Enter');
      await expect(
        caret.getByRole('button', { name: words.selectionAssist.voice.dictate, exact: true })
      ).toBeFocused();
      await page.keyboard.press('Escape');
      await expect(caret).toHaveCount(0);
      await expect(field).toBeFocused();
      await field.fill('Before after');
      await field.press('End');
      await expect(caret).toBeVisible();
      await field.press('ControlOrMeta+a');
      const edit = page.getByRole('toolbar', { name: words.selectionAssist.label, exact: true });
      await expect(edit).toBeVisible();
      await expect(caret).toHaveCount(0);
      await expect(
        edit.getByRole('button', { name: words.selectionAssist.voice.dictate, exact: true })
      ).toHaveCount(0);
      await form.getByRole('button', { name: words.common.cancel, exact: true }).focus();
      await expect(edit).toHaveCount(0);
      await expect(caret).toHaveCount(0);
    }
    expect(tickets).toEqual([]);
  });
}

for (const terminal of ['missing', 'cancelled'] as const) {
  test(`a native touch selection survives a ${terminal} pointer terminal event`, async ({
    page,
    authenticate,
    mockApi,
    browserName,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await authenticate();
    await mockApi(selectionRoutes);
    const requests: unknown[] = [];
    await mockApi([
      {
        url: '**/api/v1/tool-assists/text/selection/stream',
        method: 'POST',
        handler: async route => {
          requests.push(route.request().postDataJSON());
          await route.fulfill({
            contentType: 'text/event-stream',
            body: `data: ${JSON.stringify({ result: { proposal: { kind: 'text', text: 'Corrected' }, usage: null } })}\n\n`,
          });
        },
      },
    ]);
    await page.goto('/en/dashboard/tools/mail');
    await waitForHydration(page, 'main');
    await page.getByRole('button', { name: 'New email', exact: true }).first().click();
    const form = page.getByRole('dialog', { name: 'New email', exact: true });
    for (const kind of ['subject', 'plain', 'rich']) {
      if (kind === 'rich')
        await form.getByRole('button', { name: 'Formatting', exact: true }).click();
      const field = form.getByRole('textbox', {
        name: kind === 'subject' ? 'Subject' : 'Message',
        exact: true,
      });
      await field.fill('Before selection after');
      await beginNativeTouchSelection(field, terminal);
      // Beyond the debounce: cancellation alone is not evidence that the finger lifted.
      await page.waitForTimeout(400);
      await expect(page.getByRole('toolbar', { name: en.selectionAssist.label })).toHaveCount(0);
      await endNativeTouchSelection(field);
      const edit = page.getByRole('toolbar', { name: en.selectionAssist.label });
      await expect(edit).toBeVisible();
      await edit.getByRole('button', { name: 'Correct', exact: true }).click();
      const answer = page.getByRole('dialog', { name: 'Correct', exact: true });
      await expect(answer.getByText('Corrected', { exact: true })).toBeVisible();
      await answer.getByRole('button', { name: en.selectionAssist.apply }).click();
      if (kind === 'rich') await expect(field).toHaveText('Before Corrected after');
      else await expect(field).toHaveValue('Before Corrected after');
      await undoNativeEdit(field, browserName);
      if (kind === 'rich') await expect(field).toHaveText('Before selection after');
      else await expect(field).toHaveValue('Before selection after');
    }
    expect(requests).toEqual(
      Array.from({ length: 3 }, () => ({
        text: 'selection',
        mode: 'edit',
        action: 'fix',
        origin: 'page',
      }))
    );
  });
}

test.describe('the chat composer on a touch surface', () => {
  test.use({ hasTouch: true, viewport: { width: 390, height: 844 } });
  test('opens the editing menu after native selection and keeps the message unsent', async ({
    page,
    authenticate,
    mockApi,
    browserName,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi([...loadedChatRoutes(), ...selectionRoutes]);
    const requests: unknown[] = [];
    const sends: string[] = [];
    page.on('request', request => {
      if (new URL(request.url()).pathname.endsWith('/agents/chat/stream'))
        sends.push(request.url());
    });
    await mockApi([
      {
        url: '**/api/v1/tool-assists/text/selection/stream',
        method: 'POST',
        handler: async route => {
          requests.push(route.request().postDataJSON());
          await route.fulfill({
            contentType: 'text/event-stream',
            body: `data: ${JSON.stringify({ result: { proposal: { kind: 'text', text: 'correction' }, usage: null } })}\n\n`,
          });
        },
      },
    ]);
    await page.goto('/fr/dashboard/chat');
    const composer = page.locator('[data-chat-composer]');
    await expect(composer).toBeEnabled();
    await composer.fill('Before selection after');
    await beginNativeTouchSelection(composer, 'missing');
    await page.waitForTimeout(400);
    await expect(page.getByRole('toolbar', { name: fr.selectionAssist.label })).toHaveCount(0);
    await endNativeTouchSelection(composer);
    const toolbar = page.getByRole('toolbar', { name: fr.selectionAssist.label });
    await expect(toolbar).toBeVisible();
    await expect(toolbar.getByRole('button')).toHaveText([
      'Traduire',
      'Corriger',
      'Formater',
      'Raccourcir',
      '+ formel',
      '+ chaleureux',
      '',
    ]);
    await toolbar.getByRole('button', { name: 'Corriger', exact: true }).click();
    const answer = page.getByRole('dialog', { name: 'Corriger', exact: true });
    await expect(answer.getByText('correction', { exact: true })).toBeVisible();
    await answer.getByRole('button', { name: fr.selectionAssist.apply }).click();
    await expect(composer).toHaveValue('Before correction after');
    await undoNativeEdit(composer, browserName);
    await expect(composer).toHaveValue('Before selection after');
    expect(requests).toEqual([{ text: 'selection', mode: 'edit', action: 'fix', origin: 'page' }]);
    expect(sends).toEqual([]);
  });
});
