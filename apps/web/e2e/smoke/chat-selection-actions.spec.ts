/**
 * Selection actions (C-02) — acting on a selected passage of an answer.
 *
 * Unit tests cover the scope-refusal logic and the action wiring in jsdom.
 * Only a browser proves the part that jsdom cannot: a real `selectionchange`
 * on a rendered assistant bubble surfaces the toolbar, and a toolbar action
 * deep-links the chat (executed intent) — the whole feature lives in DOM
 * selection behaviour a component test never exercises.
 */
import type { Locator, Page } from '@playwright/test';

import { test, expect, type MockRoute } from '../fixtures';

const CONVERSATION = {
  id: '00000000-0000-4000-8000-00000000c0s2',
  user_id: '00000000-0000-4000-8000-000000000001',
  title: 'E2E selection',
  message_count: 1,
  total_tokens: 0,
  created_at: '2026-07-29T09:00:00Z',
  updated_at: '2026-07-29T10:00:00Z',
};

const ANSWER_TEXT = 'La capitale de la France est Paris.';

const ASSISTANT_MESSAGE = {
  id: '00000000-0000-4000-8000-00000000m0s2',
  role: 'assistant',
  // No id/class relied on: the sanitize pipeline strips unknown attributes,
  // so the test selects by the scope marker + visible text instead.
  content: `<p>${ANSWER_TEXT}</p>`,
  created_at: '2026-07-29T10:00:00Z',
  message_metadata: null,
};

const ROUTES: MockRoute[] = [
  { url: '**/api/v1/conversations/me', json: CONVERSATION },
  {
    url: '**/api/v1/conversations/me/messages*',
    json: {
      messages: [ASSISTANT_MESSAGE],
      conversation_id: CONVERSATION.id,
      total_count: 1,
      has_more: false,
      next_cursor: null,
    },
  },
  { url: '**/api/v1/conversations/me/totals', json: {} },
  { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
  { url: '**/api/v1/agents/runs/active', json: { active: false } },
  { url: '**/api/v1/agents/hitl/pending', json: null },
  { url: '**/api/v1/usage/**', json: {} },
];

const POSITIONED_PASSAGE = 'Ce passage doit rester lisible pendant le choix de son action.';
const MULTILINE_PASSAGE =
  'Un passage sur plusieurs lignes conserve toute son importance lorsque la fenêtre change de taille. ' +
  'Le menu reste proche de ces mots sans cacher leur début, leur milieu ou leur fin. ' +
  'Les actions sont toujours accessibles et la sélection reste la même pendant la lecture.';
const ACTION_LABELS = [
  'Expliquer',
  'Reformuler',
  'Traduire',
  'En tâche',
  'En rappel',
  'Mémoriser',
  'Poser une question',
] as const;
const SELECTION_TOOLBAR_NAME = 'Actions sur le passage sélectionné';

/** Enough genuine message content on both sides to reach either edge by scrolling. */
function positioningRoutes(): MockRoute[] {
  const before = Array.from(
    { length: 14 },
    (_, index) => `<p>Avant le passage ${index + 1}, voici une autre phrase de la réponse.</p>`
  );
  const after = Array.from(
    { length: 14 },
    (_, index) => `<p>Après le passage ${index + 1}, la réponse continue dans le fil.</p>`
  );
  return [
    ...ROUTES,
    {
      url: '**/api/v1/conversations/me/messages*',
      json: {
        messages: [
          {
            ...ASSISTANT_MESSAGE,
            content: [
              ...before,
              `<p>${POSITIONED_PASSAGE}</p>`,
              `<p>${MULTILINE_PASSAGE}</p>`,
              ...after,
            ].join(''),
          },
        ],
        conversation_id: CONVERSATION.id,
        total_count: 1,
        has_more: false,
        next_cursor: null,
      },
    },
  ];
}

/** Position real text with its real scroll ancestor, clear of the sticky header/composer. */
async function positionPassage(
  passage: Locator,
  position: 'top' | 'middle' | 'bottom'
): Promise<void> {
  // Opening history pins it to the bottom until the reader takes control.
  // A genuine wheel inside the message list ends that initial positioning.
  const readingPoint = await passage.evaluate(element => {
    for (let parent = element.parentElement; parent; parent = parent.parentElement) {
      if (
        /(auto|scroll|overlay)/.test(getComputedStyle(parent).overflowY) &&
        parent.scrollHeight > parent.clientHeight
      ) {
        const box = parent.getBoundingClientRect();
        // The reader wheels the actual message surface, clear of floating UI.
        // A wheel on an independent overlay cannot release the chat's bottom pin.
        for (const x of [box.left + box.width / 2, box.left + 16, box.right - 16]) {
          for (const y of [box.top + box.height / 2, box.top + 64, box.bottom - 64]) {
            const target = document.elementFromPoint(x, y);
            const message = target?.closest('[data-message-id]');
            // The gesture listener belongs to the message list, inside the
            // scroller. Its sticky header and empty padding do not bubble there.
            if (message && parent.contains(message)) return { x, y };
          }
        }
        throw new Error('The chat reader needs an unobstructed scroll surface');
      }
    }
    throw new Error('the assistant answer must have a nested scroll ancestor');
  });
  const page = passage.page();
  await page.mouse.move(readingPoint.x, readingPoint.y);
  await page.mouse.wheel(0, -48);
  await page.evaluate(
    () =>
      new Promise<void>(resolve =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
      )
  );
  await passage.scrollIntoViewIfNeeded();
  await passage.evaluate((element, edge) => {
    let scroller = element.parentElement;
    while (scroller) {
      const overflow = getComputedStyle(scroller).overflowY;
      if (/(auto|scroll|overlay)/.test(overflow) && scroller.scrollHeight > scroller.clientHeight) {
        break;
      }
      scroller = scroller.parentElement;
    }
    if (!scroller) throw new Error('the assistant answer must have a nested scroll ancestor');
    scroller.style.scrollBehavior = 'auto';
    const scrollBox = scroller.getBoundingClientRect();
    let top = Math.max(0, scrollBox.top) + 16;
    let bottom = Math.min(window.innerHeight, scrollBox.bottom) - 16;
    // These are the actual chat chrome bounds, not guessed header/footer heights.
    for (const child of scroller.children) {
      const style = getComputedStyle(child);
      if (style.position !== 'sticky') continue;
      const box = child.getBoundingClientRect();
      if (style.top !== 'auto') top = Math.max(top, box.bottom + 16);
      if (style.bottom !== 'auto') bottom = Math.min(bottom, box.top - 16);
    }
    const box = element.getBoundingClientRect();
    const targetTop =
      edge === 'top'
        ? top
        : edge === 'bottom'
          ? bottom - box.height
          : top + (bottom - top - box.height) / 2;
    scroller.scrollTop += box.top - targetTop;
  }, position);
  await expect(passage).toBeInViewport();
}

async function selectPassage(passage: Locator): Promise<void> {
  await passage.evaluate(element => {
    const range = document.createRange();
    range.selectNodeContents(element);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
  });
}

/** The browser's rendered boxes are the oracle: a style declaration cannot prove reachability. */
async function expectReadableMenu(toolbar: Locator): Promise<void> {
  await expect(toolbar).toBeVisible();
  await expect
    .poll(
      () =>
        toolbar.evaluate(element => {
          const box = element.getBoundingClientRect();
          const viewport = window.visualViewport;
          const left = viewport?.offsetLeft ?? 0;
          const top = viewport?.offsetTop ?? 0;
          const right = left + (viewport?.width ?? window.innerWidth);
          const bottom = top + (viewport?.height ?? window.innerHeight);
          const selection = window.getSelection();
          const range = selection && selection.rangeCount > 0 ? selection.getRangeAt(0) : null;
          const visible = { left, top, right, bottom };
          // Native range rectangles also describe lines clipped by overflow.
          // Only their intersection with the real ancestor scrollports is read.
          const ancestor = range?.commonAncestorContainer;
          for (
            let parent = ancestor instanceof Element ? ancestor : ancestor?.parentElement;
            parent;
            parent = parent.parentElement
          ) {
            const style = getComputedStyle(parent);
            const bounds = parent.getBoundingClientRect();
            if (/(auto|scroll|overlay|hidden|clip)/.test(style.overflowX)) {
              visible.left = Math.max(visible.left, bounds.left + parent.clientLeft);
              visible.right = Math.min(
                visible.right,
                bounds.left + parent.clientLeft + parent.clientWidth
              );
            }
            if (/(auto|scroll|overlay|hidden|clip)/.test(style.overflowY)) {
              visible.top = Math.max(visible.top, bounds.top + parent.clientTop);
              visible.bottom = Math.min(
                visible.bottom,
                bounds.top + parent.clientTop + parent.clientHeight
              );
            }
          }
          const rects = [...(range?.getClientRects() ?? [])]
            .map(rect => ({
              left: Math.max(rect.left, visible.left),
              right: Math.min(rect.right, visible.right),
              top: Math.max(rect.top, visible.top),
              bottom: Math.min(rect.bottom, visible.bottom),
            }))
            .filter(rect => rect.right > rect.left && rect.bottom > rect.top);
          const distances = rects.map(rect =>
            Math.hypot(
              Math.max(rect.left - box.right, box.left - rect.right, 0),
              Math.max(rect.top - box.bottom, box.top - rect.bottom, 0)
            )
          );
          return {
            selectedTextVisible: rects.length > 0,
            insideViewport:
              box.width > 0 &&
              box.height > 0 &&
              box.left >= left - 0.5 &&
              box.top >= top - 0.5 &&
              box.right <= right + 0.5 &&
              box.bottom <= bottom + 0.5,
            leavesTextReadable: rects.every(
              rect =>
                box.right <= rect.left ||
                box.left >= rect.right ||
                box.bottom <= rect.top ||
                box.top >= rect.bottom
            ),
            nearSelection: Math.min(...distances) <= 24,
            outsideFrostedPanel: element.parentElement === document.body,
          };
        }),
      {
        message:
          'selection actions must stay near visible text, inside the screen, and clear of it',
      }
    )
    .toEqual({
      selectedTextVisible: true,
      insideViewport: true,
      leavesTextReadable: true,
      nearSelection: true,
      outsideFrostedPanel: true,
    });
}

/** Select the whole assistant answer text (fires `selectionchange`). */
async function selectAnswer(page: Page): Promise<void> {
  await page.evaluate(() => {
    const scope = document.querySelector('[data-selection-scope="assistant"]');
    if (!scope) throw new Error('assistant selection scope not rendered');
    const range = document.createRange();
    range.selectNodeContents(scope);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
  });
}

test.describe('selection actions (C-02)', () => {
  test('selecting an answer surfaces the toolbar, whose action executes via the chat', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/chat');

    // The assistant answer must be rendered inside its selection scope.
    await expect(page.getByText(ANSWER_TEXT)).toBeVisible({ timeout: 30_000 });

    await selectAnswer(page);

    // The toolbar appears (selectionchange is debounced ~250 ms).
    const toolbar = page.getByRole('toolbar', { name: /chat\.selection|passage|sélection/i });
    await expect(toolbar).toBeVisible({ timeout: 10_000 });

    // A named action executes: "explain" sends through the chat pipeline.
    await toolbar.getByRole('button').first().click();
    // The composer receives the sent intent — the message list grows or the
    // input clears; either way the toolbar is dismissed (selection cleared).
    await expect(toolbar).toBeHidden({ timeout: 10_000 });
  });

  test('selecting nothing keeps the toolbar hidden', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/chat');
    await expect(page.getByText(ANSWER_TEXT)).toBeVisible({ timeout: 30_000 });

    // No selection → no toolbar.
    await expect(page.getByRole('toolbar', { name: /passage|sélection|selection/i })).toHaveCount(
      0
    );
  });

  for (const width of [320, 640, 1280]) {
    test(`the French menu stays reachable and clear of top/bottom selections at ${width}px`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await page.setViewportSize({ width, height: 800 });
      await authenticate({ language: 'fr' });
      await mockApi(positioningRoutes());
      await page.goto('/fr/dashboard/chat');

      const passage = page
        .locator('[data-selection-scope="assistant"]')
        .getByText(POSITIONED_PASSAGE, { exact: true });
      await expect(passage).toBeAttached({ timeout: 30_000 });
      await expect(page.locator('textarea')).toBeVisible();
      // Preserve the actual backdrop-filter parent that caused fixed elements
      // to use panel coordinates. This scenario must exercise that real shell.
      expect(
        await passage.evaluate(element => {
          for (let parent = element.parentElement; parent; parent = parent.parentElement) {
            if (getComputedStyle(parent).backdropFilter !== 'none') return true;
          }
          return false;
        })
      ).toBe(true);

      const toolbar = page.getByRole('toolbar', { name: SELECTION_TOOLBAR_NAME, exact: true });
      for (const edge of ['top', 'bottom'] as const) {
        await positionPassage(passage, edge);
        await selectPassage(passage);
        await expectReadableMenu(toolbar);
        for (const label of ACTION_LABELS) {
          await expect(toolbar.getByRole('button', { name: label, exact: true })).toBeVisible();
        }
        // Playwright's actionability checks detect controls clipped by an
        // ancestor or covered by another surface without executing the action.
        await toolbar.getByRole('button', { name: 'Poser une question', exact: true }).click({
          trial: true,
        });
        await expectReadableMenu(toolbar);
        await page.evaluate(() => window.getSelection()?.removeAllRanges());
        await expect(toolbar).toBeHidden();
      }
    });
  }

  test('a multiline menu follows nested scrolling and reflow without covering a selected line', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await authenticate({ language: 'fr' });
    await mockApi(positioningRoutes());
    await page.goto('/fr/dashboard/chat');

    const passage = page
      .locator('[data-selection-scope="assistant"]')
      .getByText(MULTILINE_PASSAGE, { exact: true });
    await expect(passage).toBeAttached({ timeout: 30_000 });
    await positionPassage(passage, 'middle');
    await selectPassage(passage);
    const toolbar = page.getByRole('toolbar', { name: SELECTION_TOOLBAR_NAME, exact: true });
    await expectReadableMenu(toolbar);
    const before = await page.evaluate(() => {
      const range = window.getSelection()?.getRangeAt(0);
      return {
        top: range?.getBoundingClientRect().top ?? 0,
        lines: [...(range?.getClientRects() ?? [])].filter(rect => rect.width > 0).length,
      };
    });
    expect(before.lines).toBeGreaterThan(1);

    // No new selectionchange: scroll an existing range in the actual chat scroller.
    const scrollDistance = await passage.evaluate(element => {
      let scroller = element.parentElement;
      while (scroller) {
        if (
          /(auto|scroll|overlay)/.test(getComputedStyle(scroller).overflowY) &&
          scroller.scrollHeight > scroller.clientHeight
        ) {
          const previous = scroller.scrollTop;
          scroller.style.scrollBehavior = 'auto';
          scroller.scrollTop += 48;
          return scroller.scrollTop - previous;
        }
        scroller = scroller.parentElement;
      }
      throw new Error('nested scroll ancestor disappeared');
    });
    expect(scrollDistance).toBeGreaterThan(40);
    await expect
      .poll(() =>
        page.evaluate(() => window.getSelection()?.getRangeAt(0).getBoundingClientRect().top ?? 0)
      )
      .toBeLessThan(before.top - 40);
    await expectReadableMenu(toolbar);

    // The native range survives a viewport resize and text wrapping. Position
    // it through the same scroll container, without selecting its text again.
    await page.setViewportSize({ width: 640, height: 900 });
    await positionPassage(passage, 'middle');
    await expectReadableMenu(toolbar);
    expect(await page.evaluate(() => window.getSelection()?.toString())).toBe(MULTILINE_PASSAGE);
    const afterLines = await page.evaluate(
      () =>
        [...(window.getSelection()?.getRangeAt(0).getClientRects() ?? [])].filter(
          rect => rect.width > 0
        ).length
    );
    expect(afterLines).toBeGreaterThan(before.lines);
  });

  test('keyboard navigation reaches the question action and prefills the selected passage', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: 640, height: 800 });
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/chat');
    await expect(page.getByText(ANSWER_TEXT)).toBeVisible({ timeout: 30_000 });
    await selectAnswer(page);

    const toolbar = page.getByRole('toolbar', { name: SELECTION_TOOLBAR_NAME, exact: true });
    await expectReadableMenu(toolbar);
    await toolbar.getByRole('button', { name: 'Expliquer', exact: true }).focus();
    for (const label of ACTION_LABELS.slice(1)) {
      await page.keyboard.press('Tab');
      await expect(toolbar.getByRole('button', { name: label, exact: true })).toBeFocused();
    }
    await page.keyboard.press('Enter');

    const composer = page.locator('textarea');
    await expect(composer).toHaveValue(`Au sujet de ce passage : « ${ANSWER_TEXT} » — `);
    await expect(composer).toBeFocused();
    await expect(toolbar).toBeHidden();
    await expect(page.locator('[data-selection-scope="assistant"]')).toHaveCount(1);
  });

  test('a vertically constrained menu keeps its scroll position and its final action reachable', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: 320, height: 480 });
    await authenticate({ language: 'fr' });
    await mockApi(positioningRoutes());
    await page.goto('/fr/dashboard/chat');

    const passage = page
      .locator('[data-selection-scope="assistant"]')
      .getByText(MULTILINE_PASSAGE, { exact: true });
    await expect(passage).toBeAttached({ timeout: 30_000 });
    await positionPassage(passage, 'middle');
    await selectPassage(passage);
    const toolbar = page.getByRole('toolbar', { name: SELECTION_TOOLBAR_NAME, exact: true });
    await expectReadableMenu(toolbar);
    await expect
      .poll(() => toolbar.evaluate(element => element.scrollHeight - element.clientHeight))
      .toBeGreaterThan(8);

    // Wheel the menu itself: a document-level capture listener also sees this
    // scroll, but it must not reset the menu while the person reaches its end.
    await toolbar.hover();
    await page.mouse.wheel(0, 600);
    await expect.poll(() => toolbar.evaluate(element => element.scrollTop)).toBeGreaterThan(0);
    await page.evaluate(
      () =>
        new Promise<void>(resolve =>
          requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
        )
    );
    const scrolled = await toolbar.evaluate(element => element.scrollTop);
    expect(scrolled).toBeGreaterThan(0);
    await expectReadableMenu(toolbar);
    expect(await page.evaluate(() => window.getSelection()?.toString())).toBe(MULTILINE_PASSAGE);

    // A real viewport update forces a fresh measurement. Temporarily removing
    // max-height during that measurement must not erase the person's scroll.
    await page.setViewportSize({ width: 320, height: 481 });
    await page.evaluate(
      () =>
        new Promise<void>(resolve =>
          requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
        )
    );
    await expectReadableMenu(toolbar);
    await expect
      .poll(() =>
        toolbar.evaluate(
          (element, previous) =>
            Math.abs(
              element.scrollTop - Math.min(previous, element.scrollHeight - element.clientHeight)
            ),
          scrolled
        )
      )
      .toBeLessThanOrEqual(1);
    expect(await toolbar.evaluate(element => element.scrollTop)).toBeGreaterThan(0);
    expect(await page.evaluate(() => window.getSelection()?.toString())).toBe(MULTILINE_PASSAGE);

    const question = toolbar.getByRole('button', { name: 'Poser une question', exact: true });
    await question.scrollIntoViewIfNeeded();
    await expect(question).toBeInViewport();
    await question.click();
    await expect(page.locator('textarea')).toHaveValue(
      `Au sujet de ce passage : « ${MULTILINE_PASSAGE} » — `
    );
    await expect(toolbar).toBeHidden();
  });
});
