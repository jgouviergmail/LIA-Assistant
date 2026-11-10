/** Actual native editing, modal focus and undo on the three browser engines; no provider calls. */
import AxeBuilder from '@axe-core/playwright';
import { test, expect, waitForHydration } from '../fixtures';
import { selectionRoutes as routes, undoNativeEdit } from '../fixtures/selection-assist';

test('leaving an editor closes its menu without stealing focus back', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate();
  await mockApi(routes);
  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'main');
  await page.getByRole('button', { name: 'New email', exact: true }).first().click();
  const form = page.getByRole('dialog', { name: 'New email', exact: true });
  const subject = form.getByRole('textbox', { name: 'Subject', exact: true });
  const message = form.getByRole('textbox', { name: 'Message', exact: true });
  await subject.fill('Selected subject');
  await subject.press('ControlOrMeta+a');
  await expect(
    page.getByRole('toolbar').getByRole('button', { name: 'Correct', exact: true })
  ).toBeVisible();
  await subject.press('Tab');
  await expect(subject).not.toBeFocused();
  await expect(
    page.getByRole('toolbar').getByRole('button', { name: 'Correct', exact: true })
  ).toHaveCount(0);
  await message.focus();
  await expect(page.getByRole('toolbar')).toHaveCount(0);
  await expect(message).toBeFocused();
  await message.evaluate(element => element.blur());
  await expect(message).not.toBeFocused();
  await expect(page.getByRole('toolbar')).toHaveCount(0);
});

for (const lng of ['en', 'fr'] as const) {
  test(`translation asks a language and formatting preserves explicit application (${lng})`, async ({
    page,
    authenticate,
    mockApi,
    browserName,
  }) => {
    const words =
      lng === 'fr'
        ? {
            compose: 'Nouvel email',
            subject: 'Objet',
            translate: 'Traduire',
            language: 'Langue de traduction',
            spanish: 'espagnol',
            send: 'Demander',
            apply: 'Remplacer la sélection',
            format: 'Formater',
          }
        : {
            compose: 'New email',
            subject: 'Subject',
            translate: 'Translate',
            language: 'Target language',
            spanish: 'Spanish',
            send: 'Ask',
            apply: 'Replace selection',
            format: 'Format',
          };
    await page.setViewportSize({ width: 320, height: 800 });
    await authenticate();
    await mockApi(routes);
    const requests: unknown[] = [];
    await mockApi([
      {
        url: '**/api/v1/tool-assists/text/selection/stream',
        method: 'POST',
        handler: async route => {
          requests.push(route.request().postDataJSON());
          await route.fulfill({
            contentType: 'text/event-stream',
            body: `data: ${JSON.stringify({ result: { proposal: { kind: 'text', text: 'Hola mundo' }, usage: null } })}\n\n`,
          });
        },
      },
    ]);
    await page.goto(`/${lng}/dashboard/tools/mail`);
    await waitForHydration(page, 'main');
    await page.getByRole('button', { name: words.compose, exact: true }).first().click();
    const form = page.getByRole('dialog', { name: words.compose, exact: true });
    const field = form.getByRole('textbox', { name: words.subject, exact: true });
    await field.fill('Hello world');
    await field.press('ControlOrMeta+a');
    await page
      .getByRole('toolbar')
      .getByRole('button', { name: words.translate, exact: true })
      .click();
    const bubble = page.getByRole('dialog', { name: words.translate, exact: true });
    expect(requests).toEqual([]);
    const target = bubble.getByRole('textbox', { name: words.language });
    await expect(target).toBeVisible();
    await bubble.getByRole('button', { name: words.spanish, exact: true }).click();
    await expect(target).toHaveValue(words.spanish);
    await bubble.getByRole('button', { name: words.send, exact: true }).click();
    await expect(bubble.getByText('Hola mundo', { exact: true })).toBeVisible();
    expect(requests).toEqual([
      {
        text: 'Hello world',
        mode: 'edit',
        action: 'translate',
        origin: 'page',
        target_language: words.spanish,
      },
    ]);
    await expect(field).toHaveValue('Hello world');
    expect(
      (await new AxeBuilder({ page }).include('[data-selection-assist-ui]').analyze()).violations
    ).toEqual([]);
    await bubble.getByRole('button', { name: words.apply }).click();
    await expect(field).toHaveValue('Hola mundo');
    await undoNativeEdit(field, browserName);
    await expect(field).toHaveValue('Hello world');
    await field.press('ControlOrMeta+a');
    await page
      .getByRole('toolbar')
      .getByRole('button', { name: words.format, exact: true })
      .click();
    await expect(
      page.getByRole('dialog', { name: words.format, exact: true }).getByText('Hola mundo')
    ).toBeVisible();
    expect(requests[1]).toMatchObject({ action: 'format', text: 'Hello world' });
    await expect(form).toBeVisible();
    await expect(field).toHaveValue('Hello world');
  });
}

test('empty and collapsed native editors offer no microphone when STT is disabled', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate();
  await mockApi(routes);
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
    for (const initial of ['', 'Before after']) {
      await field.fill(initial);
      await field.press('End');
      // Observe beyond the selection observer's settle interval: an immediate negative
      // assertion would also pass on the former, delayed caret-only menu.
      await page.waitForTimeout(400);
      await expect(page.getByRole('toolbar', { name: 'Ask LIA about this text' })).toHaveCount(0);
      await expect(field).toBeFocused();
    }
    await field.press('ControlOrMeta+a');
    const toolbar = page.getByRole('toolbar', { name: 'Ask LIA about this text' });
    await expect(toolbar).toBeVisible();
    await expect(toolbar.getByRole('button')).toHaveText([
      'Translate',
      'Correct',
      'Format',
      'Shorten',
      'More formal',
      'Warmer',
      '',
    ]);
    await expect(toolbar.getByRole('button', { name: 'Dictate', exact: true })).toHaveCount(0);
    await toolbar.getByRole('button', { name: 'Close', exact: true }).click();
  }
});

test('Internet shows attributed sources without navigating away or creating a record', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate();
  await mockApi([
    ...routes,
    {
      url: '**/api/v1/tool-assists/text/selection/stream',
      method: 'POST',
      handler: route =>
        route.fulfill({
          contentType: 'text/event-stream',
          body: `data: ${JSON.stringify({ result: { proposal: { kind: 'research', query: 'Email history', provider: 'perplexity', summary: 'An answer [1].', sources: [{ title: 'A documented source', url: 'https://example.test/source', excerpt: 'A source excerpt.' }] }, usage: null } })}\n\n`,
        }),
    },
  ]);
  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'main');
  await page.getByRole('button', { name: 'New email', exact: true }).first().click();
  await page.getByRole('heading', { name: 'New email', exact: true }).evaluate(element => {
    const range = document.createRange();
    range.selectNodeContents(element);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
  });
  await page.getByRole('toolbar').getByRole('button', { name: 'Internet', exact: true }).click();
  const bubble = page.getByRole('dialog', { name: 'Internet', exact: true });
  await expect(bubble.getByText('An answer [1].')).toBeVisible();
  await expect(bubble.getByRole('link', { name: 'A documented source' })).toHaveAttribute(
    'href',
    'https://example.test/source'
  );
  await expect(bubble.getByRole('button', { name: 'Replace selection' })).toHaveCount(0);
  expect(
    (await new AxeBuilder({ page }).include('[data-selection-assist-ui]').analyze()).violations
  ).toEqual([]);
  await expect(page).toHaveURL(/\/dashboard\/tools\/mail$/);
});

for (const language of [
  {
    lng: 'en',
    compose: 'New email',
    menu: 'Ask LIA about this text',
    read: 'Read',
    explain: 'Explain',
  },
  {
    lng: 'fr',
    compose: 'Nouvel email',
    menu: 'Demander à LIA sur ce texte',
    read: 'Lire',
    explain: 'Expliquer',
  },
]) {
  test(`readonly selection is keyboard-accessible in ${language.lng}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: 320, height: 900 });
    await authenticate();
    await mockApi(routes);
    await mockApi([
      {
        url: '**/api/v1/tool-assists/text/selection/stream',
        method: 'POST',
        handler: route =>
          route.fulfill({
            contentType: 'text/event-stream',
            body:
              'data: ' +
              JSON.stringify({
                result: { proposal: { kind: 'text', text: 'A new message' }, usage: null },
              }) +
              '\n\n',
          }),
      },
    ]);
    await page.goto(`/${language.lng}/dashboard/tools/mail`);
    await waitForHydration(page, 'main');
    await page.getByRole('button', { name: language.compose, exact: true }).first().click();
    const form = page.getByRole('dialog', { name: language.compose, exact: true });
    await form.getByRole('heading', { name: language.compose, exact: true }).evaluate(element => {
      const range = document.createRange();
      range.selectNodeContents(element);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
    });
    const toolbar = page.getByRole('toolbar', { name: language.menu });
    await expect(toolbar).toBeVisible();
    await page.keyboard.press('Alt+Enter');
    await expect(toolbar.getByRole('button', { name: language.read, exact: true })).toBeFocused();
    await page.keyboard.press('ArrowRight');
    await page.keyboard.press('Home');
    await page.keyboard.press('ArrowRight');
    await page.keyboard.press('ArrowRight');
    await page.keyboard.press('Enter');
    const bubble = page.getByRole('dialog', { name: language.explain, exact: true });
    await expect(bubble.getByText('A new message')).toBeVisible();
    expect(
      (await new AxeBuilder({ page }).include('[data-selection-assist-ui]').analyze()).violations
    ).toEqual([]);
    await page.keyboard.press('Escape');
    await expect(bubble).not.toBeVisible();
    await expect(form).toBeVisible();
  });
}

for (const width of [1280, 320]) {
  test(`selection edits keep the form, controlled value and undo at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
    browserName,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await authenticate();
    await mockApi(routes);
    const requests: unknown[] = [];
    await mockApi([
      {
        url: '**/api/v1/tool-assists/text/selection/stream',
        method: 'POST',
        handler: async route => {
          requests.push(route.request().postDataJSON());
          await route.fulfill({
            contentType: 'text/event-stream',
            body:
              ': waiting\n\ndata: ' +
              JSON.stringify({
                result: { proposal: { kind: 'text', text: 'Corrected' }, usage: null },
              }) +
              '\n\n',
          });
        },
      },
    ]);
    await page.goto('/en/dashboard/tools/mail');
    await waitForHydration(page, 'main');
    await page.getByRole('button', { name: 'New email', exact: true }).first().click();
    const form = page.getByRole('dialog', { name: 'New email', exact: true });
    const subject = form.getByRole('textbox', { name: 'Subject', exact: true });
    const message = form.getByRole('textbox', { name: 'Message', exact: true });
    for (const field of [subject, message]) {
      await field.fill('Before selection after');
      await field.focus();
      await field.evaluate((element: HTMLInputElement | HTMLTextAreaElement) => {
        element.setSelectionRange(7, 16);
        element.dispatchEvent(new Event('select', { bubbles: true }));
      });
      const toolbar = page.getByRole('toolbar', { name: 'Ask LIA about this text' });
      await expect(toolbar).toBeVisible();
      await expect(toolbar).toHaveCount(1);
      expect((await toolbar.boundingBox())?.width).toBeLessThanOrEqual(Math.min(640, width - 16));
      expect(requests).toHaveLength(field === subject ? 0 : 1);
      await page.getByRole('button', { name: 'Correct', exact: true }).click();
      const bubble = page.getByRole('dialog', { name: 'Correct', exact: true });
      await expect(bubble.getByText('Corrected', { exact: true })).toBeVisible();
      expect((await bubble.boundingBox())?.width).toBeLessThanOrEqual(Math.min(384, width - 16));
      await expect(form).toBeVisible();
      const scan = await new AxeBuilder({ page }).include('[data-selection-assist-ui]').analyze();
      expect(scan.violations).toEqual([]);
      await bubble.getByRole('button', { name: 'Replace selection' }).click();
      await expect(field).toHaveValue('Before Corrected after');
      await undoNativeEdit(field, browserName);
      await expect(field).toHaveValue('Before selection after');
    }
    await form.getByRole('button', { name: 'Formatting', exact: true }).click();
    const rich = form.getByRole('textbox', { name: 'Message', exact: true });
    await rich.fill('Rich selection');
    await rich.evaluate(element => {
      const range = document.createRange();
      range.selectNodeContents(element);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
    });
    await page.getByRole('button', { name: 'Correct', exact: true }).click();
    const bubble = page.getByRole('dialog', { name: 'Correct', exact: true });
    await expect(bubble.getByText('Corrected', { exact: true })).toBeVisible();
    await bubble.getByRole('button', { name: 'Replace selection' }).click();
    await expect(rich).toHaveText('Corrected');
    await undoNativeEdit(rich, browserName);
    await expect(rich).toHaveText('Rich selection');
    expect(requests).toHaveLength(3);
    expect(requests[0]).toMatchObject({ text: 'selection', mode: 'edit', action: 'fix' });
    await expect(form).toBeVisible();
  });
}

test('a resized editor covering the viewport still offers its selection actions', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 320, height: 480 });
  await authenticate();
  await mockApi(routes);
  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'main');
  await page.getByRole('button', { name: 'New email', exact: true }).first().click();
  const form = page.getByRole('dialog', { name: 'New email', exact: true });
  const message = form.getByRole('textbox', { name: 'Message', exact: true });
  await message.fill('Before selection after');
  await message.evaluate((element: HTMLTextAreaElement) => {
    // A person can resize this native textarea; force the extreme geometry deterministically.
    Object.assign(element.style, {
      position: 'fixed',
      inset: '-100px 0 auto',
      width: '100vw',
      height: '1000px',
      zIndex: '51',
    });
    element.focus();
    element.setSelectionRange(7, 16);
    element.dispatchEvent(new Event('select', { bubbles: true }));
  });
  const toolbar = page.getByRole('toolbar', { name: 'Ask LIA about this text' });
  await expect(toolbar).toBeVisible();
  await page.keyboard.press('Alt+Enter');
  await expect(toolbar.getByRole('button', { name: 'Translate', exact: true })).toBeFocused();
  const box = await toolbar.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.y + box!.height).toBeLessThanOrEqual(480);
  await toolbar.getByRole('button', { name: 'Translate', exact: true }).scrollIntoViewIfNeeded();
  await expect(toolbar.getByRole('button', { name: 'Translate', exact: true })).toBeInViewport();
  await page.keyboard.press('Escape');
  await expect(toolbar).not.toBeVisible();
  await expect(message).toHaveValue('Before selection after');
});
