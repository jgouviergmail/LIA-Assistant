/**
 * Chat journey — what each step did (owner request 2026-10-24, ADR-133).
 *
 * Hermetic: the POST /agents/chat/stream response is a mocked SSE body in the
 * shape the stream emits — a ReAct tool called twice, each call `started` then
 * finished under its `step_key`, the first with the read's counts, the second
 * failed — and the history is a mocked message carrying the persisted trace.
 * Proves in a real browser that:
 *   - the trace attached at `done` holds ONE line for the tool, its calls added
 *     up (×2, 12 results, 5 read, 1 failure), its label no longer announcing
 *     work in progress;
 *   - the same trace read back from the history says the same thing;
 *   - nothing overflows at phone width.
 *
 * No backend, LLM, or paid provider is contacted.
 */
import { test, expect, type MockRoute } from '../fixtures';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const CONVERSATION = {
  id: '00000000-0000-4000-8000-00000000c0a8',
  user_id: '00000000-0000-4000-8000-000000000001',
  title: 'E2E step outcomes',
  message_count: 0,
  total_tokens: 0,
  created_at: '2026-10-24T09:00:00Z',
  updated_at: '2026-10-24T10:00:00Z',
};

/** The display the catalogue gives the e-mail read (execution.steps.get_emails). */
const EMAIL_STEP = {
  type: 'execution_step',
  step_type: 'tool',
  step_name: 'get_emails_tool',
  emoji: '📧',
  i18n_key: 'get_emails',
  category: 'tool',
};

/** The line every assertion reads: one tool, its calls added up. */
const SETTLED_LINE = 'Récupération des e-mails — ×2 · 12 résultats · 5 lus · 1 échec';

function step(metadata: Record<string, unknown>): string {
  return `data: ${JSON.stringify({ type: 'execution_step', content: '', metadata: { ...EMAIL_STEP, ...metadata } })}\n\n`;
}

/** SSE body: two calls of one tool — counts on the first, a failure on the second. */
function sseTwoCalls(): string {
  return (
    step({ status: 'started', step_key: 'call_a' }) +
    step({ status: 'started', step_key: 'call_b' }) +
    step({ status: 'completed', step_key: 'call_a', outcome: { failed: 0, found: 12, shown: 5 } }) +
    step({ status: 'failed', step_key: 'call_b', outcome: { failed: 1 } }) +
    'data: {"type":"token","content":"J\'ai trouvé 12 e-mails."}\n\n' +
    'data: {"type":"done","content":"","metadata":{"duration_ms":1200}}\n\n'
  );
}

function routes(history: unknown[]): MockRoute[] {
  return [
    { url: '**/api/v1/conversations/me', json: CONVERSATION },
    {
      url: '**/api/v1/conversations/me/messages*',
      json: {
        messages: history,
        conversation_id: CONVERSATION.id,
        total_count: history.length,
        has_more: false,
        next_cursor: null,
      },
    },
    { url: '**/api/v1/conversations/me/totals', json: {} },
    { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
    { url: '**/api/v1/agents/runs/active', json: { active: false } },
    { url: '**/api/v1/agents/hitl/pending', json: null },
    { url: '**/api/v1/usage/**', json: {} },
    {
      url: '**/api/v1/agents/chat/stream',
      method: 'POST',
      handler: async route => {
        await route.fulfill({ status: 200, contentType: 'text/event-stream', body: sseTwoCalls() });
      },
    },
  ];
}

/** An answer read back from the history, carrying the trace the server persisted. */
const PERSISTED_ANSWER = {
  id: '00000000-0000-4000-8000-00000000c0a9',
  role: 'assistant',
  content: "J'ai trouvé 12 e-mails.",
  created_at: '2026-10-24T10:00:00Z',
  message_metadata: {
    execution_trace: {
      steps: [
        {
          emoji: '📧',
          i18n_key: 'get_emails',
          category: 'tool',
          outcome: { calls: 2, found: 12, shown: 5, failed: 1 },
        },
      ],
      duration_ms: 1200,
    },
  },
};

async function openTrace(page: import('@playwright/test').Page): Promise<void> {
  const toggle = page.getByRole('button', { name: "Afficher les détails d'exécution" });
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
}

for (const { device, viewport } of [
  { device: 'desktop', viewport: { width: 1280, height: 900 } },
  { device: 'phone', viewport: { width: 375, height: 812 } },
]) {
  test.describe(`chat step outcomes (${device})`, () => {
    test.use({ viewport });

    test('the trace attached to the answer adds the calls of one tool up', async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await authenticate();
      await mockApi(routes([]));

      await page.goto('/fr/dashboard/chat');
      await awaitStyledPage(page, `chat step outcomes (${device})`);
      const textarea = page.locator('textarea');
      await textarea.fill('Cherche mes e-mails de la semaine');
      await textarea.press('Enter');

      await expect(page.getByText("J'ai trouvé 12 e-mails.")).toBeVisible();
      await openTrace(page);
      // ONE line for the tool, never one per call.
      const lines = page.getByRole('listitem').filter({ hasText: 'Récupération des e-mails' });
      await expect(lines).toHaveCount(1);
      await expect(lines.first()).toHaveText(`📧${SETTLED_LINE}`);
      await expectNoOverflow(page, `chat step outcomes live (${device})`);
    });

    test('the trace read back from the history says the same thing', async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await authenticate();
      await mockApi(routes([PERSISTED_ANSWER]));

      await page.goto('/fr/dashboard/chat');
      await awaitStyledPage(page, `chat step outcomes (${device})`);

      await expect(page.getByText("J'ai trouvé 12 e-mails.")).toBeVisible();
      await openTrace(page);
      await expect(
        page.getByRole('listitem').filter({ hasText: 'Récupération des e-mails' })
      ).toHaveText(`📧${SETTLED_LINE}`);
      await expectNoOverflow(page, `chat step outcomes history (${device})`);
    });
  });
}
