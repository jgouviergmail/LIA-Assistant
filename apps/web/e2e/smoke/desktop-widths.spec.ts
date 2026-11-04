/**
 * What a large screen opens (owner, 2026-11-04): the interface breathes when the
 * screen allows it, and nothing moves where it does not.
 *
 * Every page and the header stand on one rail, whose ceiling is half as wide again as
 * the 1280 px it was; the chat's thread and composer gain the same half; and the words
 * of a long text keep a reading width that its tables, code and cards do not have.
 * Below `lg` none of it applies: a phone and a tablet draw what they drew.
 *
 * Geometry, so a browser is the only oracle: jsdom applies no stylesheet. The Tools
 * section keeps the whole window (`workbench-matrix.spec.ts`).
 */
import type { Locator, Page } from '@playwright/test';

import { test, expect, loadedChatRoutes, waitForHydration, type MockRoute } from '../fixtures';
import { expectNoOverflow } from './overflow-report';

/** The ceilings in pixels: `--container-*` in `src/styles/globals.css`. */
const RAIL = 1920;
const THREAD = 1536;
const COMPOSER = 1344;
const READING = 1024;
/** What the thread and the composer keep below `lg`: `max-w-5xl`, `max-w-4xl`. */
const TABLET_THREAD = 1024;
const TABLET_COMPOSER = 896;

const WORDS =
  'The supplier proposed a later date than the brief, so the team kept the agreed scope and asked for a written confirmation before anything is announced. '.repeat(
    8
  );

/** An answer with all three: words, a table, and a card with words of its own. */
const LONG_ANSWER: MockRoute = {
  url: '**/api/v1/conversations/me/messages*',
  json: {
    messages: [
      {
        id: '00000000-0000-4000-8000-00000000m0w1',
        role: 'assistant',
        content:
          `<div class="lia-response"><p>${WORDS}</p>` +
          '<table><thead><tr><th>Step</th><th>Owner</th></tr></thead>' +
          '<tbody><tr><td>Confirm the date</td><td>Alex</td></tr></tbody></table></div>' +
          `<div class="lia-card"><p>${WORDS}</p></div>`,
        created_at: '2026-11-04T10:00:00Z',
      },
    ],
    conversation_id: '00000000-0000-4000-8000-00000000c0h1',
    total_count: 1,
    has_more: false,
    next_cursor: null,
  },
};

/** Where a box starts and ends across the window, in whole pixels. */
async function span(box: Locator): Promise<{ left: number; right: number }> {
  const drawn = await box.boundingBox();
  if (!drawn) throw new Error('the box is not drawn');
  return { left: Math.round(drawn.x), right: Math.round(drawn.x + drawn.width) };
}

async function width(box: Locator): Promise<number> {
  const { left, right } = await span(box);
  return right - left;
}

/** The composer's own frame: the nearest centred box around its field. */
function composer(page: Page): Locator {
  return page
    .locator('.lia-chat-footer textarea')
    .locator('xpath=ancestor::div[contains(concat(" ", @class, " "), " mx-auto ")][1]');
}

/** The thread: the column every message of the chat stands in. */
function thread(page: Page): Locator {
  return page.locator('[class*="max-w-chat-thread"]');
}

async function openLongAnswer(
  page: Page,
  authenticate: () => Promise<unknown>,
  mockApi: (routes: MockRoute[]) => Promise<void>
): Promise<Locator> {
  await authenticate();
  await mockApi([...loadedChatRoutes(), LONG_ANSWER]);
  await page.goto('/en/dashboard/chat');
  const bubble = page.locator('.message-bubble-assistant');
  await expect(bubble).toBeVisible();
  return bubble;
}

test('the page and the header stand on one rail, centred past its ceiling', async ({
  page,
  authenticate,
}) => {
  await authenticate();
  await page.goto('/en/dashboard/faq');
  await waitForHydration(page, 'main');

  for (const sample of [
    { width: 1023, gutter: 24 },
    { width: 1024, gutter: 32 },
    { width: 1280, gutter: 32 },
    { width: 1536, gutter: 32 },
    { width: RAIL, gutter: 32 },
    { width: 2560, gutter: 32 },
  ]) {
    await page.setViewportSize({ width: sample.width, height: 900 });
    const left = Math.max(0, (sample.width - RAIL) / 2);
    const rail = { left, right: sample.width - left };

    await expect.poll(() => span(page.locator('main')), `${sample.width}px`).toEqual(rail);
    await expect
      .poll(() => span(page.locator('header.lia-dashboard-header > div')), `${sample.width}px`)
      .toEqual(rail);
    await expect
      .poll(async () => (await span(page.getByRole('heading', { level: 1 }))).left)
      .toBe(left + sample.gutter);
    await expectNoOverflow(page, `rail ${sample.width}px`);
  }
});

test('the chat gains half its width, and its words stay at the reading width', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: RAIL, height: 1080 });
  const bubble = await openLongAnswer(page, authenticate, mockApi);

  expect(await width(thread(page))).toBe(THREAD);
  expect(await width(composer(page))).toBe(COMPOSER);
  expect(await width(bubble.locator('.lia-response p'))).toBe(READING);
  expect(await width(bubble.locator('table'))).toBeGreaterThan(READING);
  expect(await width(bubble.locator('.lia-card p'))).toBeGreaterThan(READING);
  await expectNoOverflow(page, 'chat 1920px');
});

test('a thread stops at its ceiling on the widest window', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 2560, height: 1080 });
  await openLongAnswer(page, authenticate, mockApi);

  expect(await width(thread(page))).toBe(THREAD);
  expect(await width(composer(page))).toBe(COMPOSER);
  await expectNoOverflow(page, 'chat 2560px');
});

test('a laptop gains the room its panel has, past the 1024 px thread of a tablet', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await openLongAnswer(page, authenticate, mockApi);

  expect(await width(thread(page))).toBeGreaterThan(TABLET_THREAD);
  expect(await width(composer(page))).toBeGreaterThan(TABLET_COMPOSER);
  await expectNoOverflow(page, 'chat 1280px');
});

for (const sample of [
  { width: 390, height: 844, composer: null },
  { width: 1023, height: 800, composer: TABLET_COMPOSER },
] as const) {
  test(`at ${sample.width}px the chat keeps its widths and its words their whole column`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: sample.width, height: sample.height });
    const bubble = await openLongAnswer(page, authenticate, mockApi);

    expect(await width(thread(page))).toBeLessThanOrEqual(TABLET_THREAD);
    if (sample.composer) expect(await width(composer(page))).toBe(sample.composer);
    const words = await width(bubble.locator('.lia-response p'));
    const column = await width(bubble.locator('.lia-response'));
    expect(words).toBe(column);
    await expectNoOverflow(page, `chat ${sample.width}px`);
  });
}

for (const sample of [
  { type: 'md', words: 'main .markdown-content p' },
  { type: 'txt', words: 'main pre > span' },
] as const) {
  test(`a ${sample.type} document keeps its reading width on a wide window`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const id = '00000000-0000-4000-8000-00000000d001';
    await page.setViewportSize({ width: RAIL, height: 1080 });
    await authenticate();
    await mockApi([
      {
        url: `**/api/v1/attachments/${id}`,
        handler: route =>
          route.fulfill({ status: 200, contentType: 'text/plain', body: `${WORDS}\n\n${WORDS}` }),
      },
    ]);

    await page.goto(`/en/dashboard/documents/${id}?name=Plan.${sample.type}&type=${sample.type}`);
    const words = page.locator(sample.words).first();
    await expect(words).toBeVisible();

    expect(await width(words)).toBe(READING);
    await expectNoOverflow(page, `${sample.type} document 1920px`);
  });
}

test('a FAQ answer keeps its reading width while its row runs the page', async ({
  page,
  authenticate,
}) => {
  await page.setViewportSize({ width: RAIL, height: 1080 });
  await authenticate();
  await page.goto('/en/dashboard/faq');
  const question = page.locator('h3 button').first();
  await expect(question).toBeVisible({ timeout: 30_000 });
  await waitForHydration(page, 'h3 button');

  await question.click();
  const answer = page.locator('main [role="region"][data-state="open"] > div > div').first();
  await expect(answer).toBeVisible();

  expect(await width(answer)).toBe(READING);
  expect(await width(question)).toBeGreaterThan(READING);
  await expectNoOverflow(page, 'faq 1920px');
});
