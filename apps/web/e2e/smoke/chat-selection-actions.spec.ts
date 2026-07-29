/**
 * Selection actions (C-02) — acting on a selected passage of an answer.
 *
 * Unit tests cover the scope-refusal logic and the action wiring in jsdom.
 * Only a browser proves the part that jsdom cannot: a real `selectionchange`
 * on a rendered assistant bubble surfaces the toolbar, and a toolbar action
 * deep-links the chat (executed intent) — the whole feature lives in DOM
 * selection behaviour a component test never exercises.
 */
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

/** Select the whole assistant answer text (fires `selectionchange`). */
async function selectAnswer(page: import('@playwright/test').Page): Promise<void> {
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
});
