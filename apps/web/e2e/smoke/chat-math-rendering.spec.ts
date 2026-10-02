/**
 * Chat — a formula is laid out by the stylesheet the app serves.
 *
 * From 2026-07-20 the chat rendered formulas with KaTeX 0.16 while the layout
 * imported the 0.18 stylesheet, whose layout classes had been renamed: struts,
 * script sizes, over- and underlines silently lost their rules, and every unit
 * test stayed green because jsdom applies no stylesheet. Hermetic, in a real
 * engine: an answer carrying display math is streamed, and the first box of the
 * formula and its strut must wear the computed style KaTeX's stylesheet gives
 * them. They are located by STRUCTURE, never by class name — the class names
 * are exactly what changed between versions.
 */
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';
import { awaitStyledPage } from './overflow-report';

const NL = String.fromCharCode(10);
const BS = String.fromCharCode(92);

const CONVERSATION = {
  id: '00000000-0000-4000-8000-0000000ca7e5',
  user_id: '00000000-0000-4000-8000-000000000001',
  title: 'E2E math rendering',
  message_count: 0,
  total_tokens: 0,
  created_at: '2026-10-02T09:00:00Z',
  updated_at: '2026-10-02T09:00:00Z',
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

/** Display math, as a model writes it: the `$$` fences on their own lines. */
const ANSWER = [
  'Voici la formule :',
  '',
  '$$',
  `x_{1,2}=${BS}frac{-b${BS}pm${BS}sqrt{b^2-4ac}}{2a}`,
  '$$',
  '',
].join(NL);

function sseAnswer(answer: string): string {
  const chunks: string[] = [];
  for (let i = 0; i < answer.length; i += 24) {
    chunks.push(
      'data: {"type":"token","content":' + JSON.stringify(answer.slice(i, i + 24)) + '}' + NL + NL
    );
  }
  return chunks.join('') + 'data: {"type":"done","content":"","metadata":null}' + NL + NL;
}

function routes(): MockRoute[] {
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
          body: sseAnswer(ANSWER),
        });
      },
    },
  ];
}

test('a display formula is laid out by the served KaTeX stylesheet', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate();
  await mockApi(routes());

  await page.goto('/fr/dashboard/chat');
  await waitForHydration(page);
  await awaitStyledPage(page, 'chat math rendering');

  await page.locator('textarea').fill('Écris la formule du second degré');
  await page.keyboard.press('Enter');

  const formula = page.locator('.message-bubble-assistant .katex-display .katex-html').first();
  await expect(formula).toBeVisible({ timeout: 15_000 });

  const layout = await formula.evaluate(html => {
    const base = html.firstElementChild as HTMLElement;
    const strut = base.firstElementChild as HTMLElement;
    return {
      basePosition: getComputedStyle(base).position,
      baseWhiteSpace: getComputedStyle(base).whiteSpace,
      strutDisplay: getComputedStyle(strut).display,
    };
  });
  expect(layout).toEqual({
    basePosition: 'relative',
    baseWhiteSpace: 'nowrap',
    strutDisplay: 'inline-block',
  });
});
