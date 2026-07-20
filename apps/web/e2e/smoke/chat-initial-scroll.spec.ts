/**
 * Chat journey — a long conversation opens at its LAST message.
 *
 * Hermetic: history is served by a cursor-aware mock; everything else dies on
 * the 501 catch-all. No backend, LLM or paid provider is contacted.
 *
 * Why a browser test: jsdom performs no layout, so `scrollHeight` is whatever a
 * stub says and every scroll assertion is vacuous. This defect lived entirely
 * in the layout — the page wraps the message list in its own
 * `overflow-y-auto` box, so the list's inner container never scrolls and
 * reports `scrollHeight === clientHeight` forever. Only a real engine shows it.
 *
 * Two oracles, both from the live layout:
 *   1. distance to the bottom of the scrolling box — what the reader sees;
 *   2. the number of rendered messages — an unprompted prepend loop used to
 *      pull 780 messages in three seconds while the reader sat on the first.
 */
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';

const CONVERSATION = {
  id: '00000000-0000-4000-8000-00000000c003',
  user_id: '00000000-0000-4000-8000-000000000001',
  title: 'E2E initial scroll',
  message_count: 60,
  total_tokens: 0,
  created_at: '2026-07-18T09:00:00Z',
  updated_at: '2026-07-18T10:00:00Z',
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

const PAGE_SIZE = 60;
const NL = String.fromCharCode(10);
const FENCE = '```';

/**
 * Every third message carries a fenced code block. MarkdownContent renders it
 * through a React.lazy CodeBlock, so the first paint is a Suspense fallback and
 * the real (taller) block lands later — the late growth a plain-text fixture
 * never exercises.
 */
function body(index: number): string {
  if (index % 3 !== 0) {
    return (
      'Message ' +
      index +
      '. Une ligne de contenu suffisamment longue pour occuper plusieurs ' +
      'lignes a l ecran et forcer la liste a deborder largement du viewport.'
    );
  }
  const code = Array.from(
    { length: 12 },
    (_, l) => 'def etape_' + l + '(valeur):' + NL + '    return valeur * ' + l
  ).join(NL);
  return 'Message ' + index + ' :' + NL + NL + FENCE + 'python' + NL + code + NL + FENCE + NL;
}

/** Cursor-aware: each page returns DIFFERENT, older ids, so a prepend is real. */
function historyPage(pageIndex: number) {
  const newest = 1000 - pageIndex * PAGE_SIZE;
  return {
    messages: Array.from({ length: PAGE_SIZE }, (_, i) => {
      const index = newest - i;
      return {
        id: '00000000-0000-4000-8000-' + String(index).padStart(12, '0'),
        conversation_id: CONVERSATION.id,
        role: index % 2 === 1 ? 'user' : 'assistant',
        content: body(index),
        created_at: new Date(Date.UTC(2026, 6, 18, 9, 0, index)).toISOString(),
        tokens_in: null,
        tokens_out: null,
        tokens_cache: null,
        cost_eur: null,
        google_api_requests: null,
        stt_provider: null,
        stt_audio_duration_seconds: null,
      };
    }),
    conversation_id: CONVERSATION.id,
    total_count: 1000,
    has_more: true,
    next_cursor: String(pageIndex + 1),
  };
}

function baseRoutes(): MockRoute[] {
  return [
    { url: '**/api/v1/config', json: APP_CONFIG },
    { url: '**/api/v1/conversations/me', json: CONVERSATION },
    {
      url: '**/api/v1/conversations/me/messages*',
      handler: async route => {
        const before = new URL(route.request().url()).searchParams.get('before');
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(historyPage(before ? Number(before) : 0)),
        });
      },
    },
    { url: '**/api/v1/conversations/me/totals', json: {} },
    { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
    { url: '**/api/v1/agents/runs/active', json: { active: false } },
    { url: '**/api/v1/agents/hitl/pending', json: null },
    { url: '**/api/v1/usage/**', json: {} },
  ];
}

/** Geometry of the box that actually scrolls, read from the live layout. */
async function geometry(page: import('@playwright/test').Page) {
  return page.evaluate(() => {
    const boxes = Array.from(document.querySelectorAll<HTMLElement>('.overflow-y-auto'));
    const el = boxes.find(b => b.scrollHeight > b.clientHeight) ?? boxes[0];
    return {
      distanceToBottom: el ? Math.round(el.scrollHeight - el.clientHeight - el.scrollTop) : -1,
      scrollHeight: el ? el.scrollHeight : -1,
      clientHeight: el ? el.clientHeight : -1,
      messages: document.querySelectorAll('[data-message-id]').length,
    };
  });
}

test.describe('chat initial scroll position', () => {
  test('opens at the last message and stays there', async ({ page, authenticate, mockApi }) => {
    await authenticate();
    await mockApi(baseRoutes());

    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);
    await expect(page.getByText('Message 1000', { exact: false })).toBeAttached();

    // Let the layout settle: lazy code blocks resolve and the pin window ends.
    await page.waitForTimeout(2500);
    const g = await geometry(page);

    // Sanity — the list really overflows, so the assertions below mean something.
    expect(g.scrollHeight).toBeGreaterThan(g.clientHeight * 2);
    // The reader is at the bottom. Landing at the top yields thousands of px.
    expect(g.distanceToBottom).toBeLessThanOrEqual(8);
  });

  test('lets the reader scroll away during the settle window', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // The list is re-pinned to the bottom every frame while the layout settles.
    // That must never fight the reader: a scroll gesture inside the window has
    // to stop the pinning at once, or the viewport is yanked back under them.
    await authenticate();
    await mockApi(baseRoutes());

    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);
    await page.waitForTimeout(400); // still inside the pin window

    await page.mouse.move(640, 400);
    await page.mouse.wheel(0, -4000);
    await page.waitForTimeout(1500); // outlast the window

    const g = await geometry(page);
    expect(g.distanceToBottom).toBeGreaterThan(500);
  });

  test('does not paginate on its own while loading', async ({ page, authenticate, mockApi }) => {
    // The sentinel sits at the top of a list that starts at scrollTop 0, so it
    // is trivially "visible" during load. Acting on that pulled page after
    // page — 780 messages in three seconds — and each prepend suppressed the
    // corrective scroll, which is what stranded the reader at the very top.
    await authenticate();
    await mockApi(baseRoutes());

    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);
    await page.waitForTimeout(2500);

    const g = await geometry(page);
    expect(g.messages).toBe(PAGE_SIZE);
  });
});
