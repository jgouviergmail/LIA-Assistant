/**
 * Chat — a long line of code stays reachable, and says so.
 *
 * Reported 2026-09-17: « a line of code overflows the card on the right, the
 * whole line cannot be read ». Measured on the running app the block WAS a
 * scroll container — but a fence without a language never reached CodeBlock
 * (an inline chip in a bare <pre>), and an overlay scrollbar (Chromium ≥ 121
 * on Windows 11, every touch device) shows nothing until the pointer is over
 * the block. Hermetic, in a real engine (jsdom performs no layout):
 * - every code block, with or without a language, in the Markdown and in the
 *   rich-HTML mode, renders inside CodeBlock's scroll box;
 * - the box scrolls horizontally, its scrollbar takes layout space (a styled
 *   scrollbar is never an overlay one) and the block announces its overflow
 *   so the edge cue can be drawn;
 * - the last character of the line is reachable by scrolling;
 * - nothing pushes the page wider than the viewport, desktop and 390 px.
 */
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const NL = String.fromCharCode(10);

const CONVERSATION = {
  id: '00000000-0000-4000-8000-00000000c0de',
  user_id: '00000000-0000-4000-8000-000000000001',
  title: 'E2E code blocks',
  message_count: 0,
  total_tokens: 0,
  created_at: '2026-09-17T09:00:00Z',
  updated_at: '2026-09-17T09:00:00Z',
};

const APP_CONFIG = {
  sse: { heartbeat_interval_seconds: 15 },
  rate_limits: { enabled: false, per_minute: 60, burst: 10 },
  i18n: { supported_languages: ['fr', 'en'], default_language: 'fr' },
  features: {
    tool_approval_enabled: true,
    attachments_enabled: true,
    rag_spaces_enabled: false,
    rag_spaces_embedding_model: '',
  },
  api_version: 'v1',
};

const EMPTY_HISTORY = {
  messages: [],
  conversation_id: CONVERSATION.id,
  total_count: 0,
  has_more: false,
  next_cursor: null,
};

/** One line three times wider than any bubble, ending on a sentinel. */
const SENTINEL = 'END_OF_LINE';
const LONG_LINE =
  'def very_long_function_name_' +
  'x'.repeat(120) +
  '(argument_one, argument_two, argument_three):  # ' +
  SENTINEL;

const MARKDOWN_ANSWER =
  'Voici le code :' + NL + NL + '```' + NL + LONG_LINE + NL + '    return 1' + NL + '```' + NL;

const HTML_ANSWER =
  '<div class="lia-response"><h2>Code</h2><p>Voici.</p>' +
  '<pre><code class="language-python">' +
  LONG_LINE +
  NL +
  '    return 1' +
  NL +
  '</code></pre></div>';

function sseAnswer(answer: string): string {
  const chunks: string[] = [];
  for (let i = 0; i < answer.length; i += 24) {
    chunks.push(
      'data: {"type":"token","content":' + JSON.stringify(answer.slice(i, i + 24)) + '}' + NL + NL
    );
  }
  return chunks.join('') + 'data: {"type":"done","content":"","metadata":null}' + NL + NL;
}

function routes(answer: string): MockRoute[] {
  return [
    { url: '**/api/v1/config', json: APP_CONFIG },
    { url: '**/api/v1/conversations/me', json: CONVERSATION },
    { url: '**/api/v1/conversations/me/messages*', json: EMPTY_HISTORY },
    { url: '**/api/v1/conversations/me/totals', json: {} },
    { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
    { url: '**/api/v1/agents/runs/active', json: { active: false } },
    { url: '**/api/v1/agents/hitl/pending', json: null },
    { url: '**/api/v1/usage/**', json: {} },
    {
      url: '**/api/v1/agents/chat/stream',
      method: 'POST',
      handler: async route => {
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body: sseAnswer(answer),
        });
      },
    },
  ];
}

interface ScrollBoxReport {
  overflowX: string;
  clientWidth: number;
  scrollWidth: number;
  bubbleRight: number;
  boxRight: number;
  /** The right-edge cue: the frame's ::after content while there is more to the right. */
  edgeCue: string;
}

/**
 * The scroll box, measured. The scrollbar itself is NOT measured: Playwright
 * launches headless Chromium with `--hide-scrollbars`, so its height reads 0
 * whatever the stylesheet says — the classic-scrollbar rule is a CSS fact
 * (`::-webkit-scrollbar` styling opts out of overlay scrollbars), the edge cue
 * is what this engine can see.
 */
async function measureScrollBox(page: import('@playwright/test').Page): Promise<ScrollBoxReport> {
  const box = page.locator('.message-bubble-assistant .code-scroll').first();
  await expect(box).toBeVisible({ timeout: 15_000 });
  return box.evaluate(el => {
    const cs = getComputedStyle(el);
    const bubble = el.closest('.message-bubble-assistant') as HTMLElement;
    const frame = el.closest('.code-scroll-frame') as HTMLElement;
    return {
      overflowX: cs.overflowX,
      clientWidth: el.clientWidth,
      scrollWidth: el.scrollWidth,
      bubbleRight: Math.round(bubble.getBoundingClientRect().right),
      boxRight: Math.round(el.getBoundingClientRect().right),
      edgeCue: getComputedStyle(frame, '::after').content,
    };
  });
}

/** Scroll the box to its end and tell whether the sentinel's glyphs sit inside the viewport. */
async function scrollToEndAndFindSentinel(page: import('@playwright/test').Page): Promise<boolean> {
  const box = page.locator('.message-bubble-assistant .code-scroll').first();
  return box.evaluate((el, sentinel) => {
    el.scrollLeft = el.scrollWidth;
    const range = document.createRange();
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let node: Node | null = walker.nextNode();
    while (node) {
      const index = node.textContent?.indexOf(sentinel) ?? -1;
      if (index >= 0) {
        range.setStart(node, index);
        range.setEnd(node, index + sentinel.length);
        return range.getBoundingClientRect().right <= window.innerWidth;
      }
      node = walker.nextNode();
    }
    return false;
  }, SENTINEL);
}

const CASES = [
  { label: 'markdown fence without a language', answer: MARKDOWN_ANSWER },
  { label: 'rich-HTML pre>code', answer: HTML_ANSWER },
] as const;

for (const { label, answer } of CASES) {
  for (const width of [1280, 390]) {
    test(`${label} at ${width}px scrolls, shows its scrollbar, keeps the page inside the viewport`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await page.setViewportSize({ width, height: 900 });
      await authenticate();
      await mockApi(routes(answer));

      await page.goto('/fr/dashboard/chat');
      await waitForHydration(page);
      await awaitStyledPage(page, `code-block ${label} ${width}`);

      await page.locator('textarea').fill('Montre-moi le code');
      await page.keyboard.press('Enter');

      // The announce is an effect after commit — awaited, never read once.
      const frame = page.locator('.message-bubble-assistant .code-scroll-frame').first();
      await expect(frame).toHaveAttribute('data-overflowing', 'true', { timeout: 15_000 });
      await expect(frame).toHaveAttribute('data-scrolled-end', 'false');

      const report = await measureScrollBox(page);
      expect(['auto', 'scroll']).toContain(report.overflowX);
      expect(report.scrollWidth).toBeGreaterThan(report.clientWidth);
      expect(report.boxRight).toBeLessThanOrEqual(report.bubbleRight);
      // The edge cue is drawn while there is more to the right...
      expect(report.edgeCue).toBe('""');

      // ...and gone once the end is reached, where the whole line is readable.
      expect(await scrollToEndAndFindSentinel(page)).toBe(true);
      await expect(frame).toHaveAttribute('data-scrolled-end', 'true');
      expect((await measureScrollBox(page)).edgeCue).toBe('none');

      // No bare <pre> around the block: the block IS the unit.
      expect(await page.locator('.message-bubble-assistant pre').count()).toBe(1);

      await expectNoOverflow(page, `code-block ${label} ${width}`);
    });
  }
}
