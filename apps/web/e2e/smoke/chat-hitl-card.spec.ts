/**
 * Chat journey — HITL approval card (Lot 1 P1-V1).
 *
 * Hermetic: the pending interrupt is served by the mocked
 * GET /agents/hitl/pending (rehydration path — the card cannot come from
 * archived history), the POST /agents/chat/stream response is a mocked SSE
 * body, everything else dies on the 501 catch-all. Proves in a real browser
 * accessibility tree that:
 *   - the card rehydrates from a pending interrupt (no message sent);
 *   - a one-click cancel resolves it (Annulé badge, buttons gone);
 *   - a stale decision (error hitl_decision_stale) expires it;
 *   - a typed reply while the card is shown resolves it via_text.
 *
 * No backend, LLM, or paid provider is contacted.
 */
import { test, expect, type MockRoute } from '../fixtures';

const CONVERSATION = {
  id: '00000000-0000-4000-8000-00000000c001',
  user_id: '00000000-0000-4000-8000-000000000001',
  title: 'E2E HITL',
  message_count: 0,
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

/** Pending tool_confirmation interrupt (shape from the T0.3 runtime capture). */
const PENDING_TOOL_CONFIRMATION = {
  message_id: 'hitl_e2e_tool_1',
  action_requests: [
    {
      type: 'tool_confirmation',
      tool_name: 'send_email_tool',
      tool_args: { to: 'e2e@example.com', subject: 'Bonjour' },
      available_actions: [
        { action: 'confirm', label: 'confirm', style: 'primary' },
        { action: 'cancel', label: 'cancel', style: 'destructive' },
      ],
      registry_ids: [],
    },
  ],
  interrupt_ts: '2026-07-18T10:00:00+00:00',
  generated_question: "Confirmer l'envoi de l'e-mail ?",
};

/** SSE body: a bare done chunk (resolves a submitted card). */
function sseDone(): string {
  return 'data: {"type":"done","content":"","metadata":null}\n\n';
}

/** SSE body: the typed stale error the router emits for an expired decision. */
function sseStale(): string {
  return (
    'data: {"type":"error","content":"Cette demande n\'est plus active.",' +
    '"metadata":{"error_code":"hitl_decision_stale"}}\n\n' +
    'data: {"type":"done","content":"","metadata":null}\n\n'
  );
}

/** Common mocks for a chat page with one pending interrupt. */
function baseRoutes(pendingBody: unknown, streamBody: () => string): MockRoute[] {
  return [
    { url: '**/api/v1/config', json: APP_CONFIG },
    { url: '**/api/v1/conversations/me', json: CONVERSATION },
    {
      url: '**/api/v1/conversations/me/messages*',
      json: {
        messages: [],
        conversation_id: CONVERSATION.id,
        total_count: 0,
        has_more: false,
        next_cursor: null,
      },
    },
    { url: '**/api/v1/conversations/me/totals', json: {} },
    { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
    { url: '**/api/v1/agents/runs/active', json: { active: false } },
    { url: '**/api/v1/agents/hitl/pending', json: pendingBody },
    { url: '**/api/v1/usage/**', json: {} },
    {
      url: '**/api/v1/agents/chat/stream',
      method: 'POST',
      handler: async route => {
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body: streamBody(),
        });
      },
    },
  ];
}

const CARD = 'section[aria-label="Approbation requise"]';

test.describe('chat HITL approval card', () => {
  test('rehydrates from a pending interrupt without sending a message', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(baseRoutes(PENDING_TOOL_CONFIRMATION, sseDone));

    await page.goto('/fr/dashboard/chat');

    const card = page.locator(CARD);
    await expect(card).toBeVisible();
    await expect(card.getByText('send_email_tool')).toBeVisible();
    await expect(card.getByRole('button', { name: 'Confirmer' })).toBeEnabled();
    await expect(card.getByRole('button', { name: 'Annuler' })).toBeEnabled();
  });

  test('one-click cancel clears the card when the turn completes', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(baseRoutes(PENDING_TOOL_CONFIRMATION, sseDone));

    await page.goto('/fr/dashboard/chat');
    const card = page.locator(CARD);
    await card.getByRole('button', { name: 'Annuler' }).click();

    // User feedback 2026-07-19: no lingering resolved card — the reply
    // bubble is the outcome feedback, the card disappears at done.
    await expect(card).toHaveCount(0);
  });

  test('a stale decision expires the card', async ({ page, authenticate, mockApi }) => {
    await authenticate();
    await mockApi(baseRoutes(PENDING_TOOL_CONFIRMATION, sseStale));

    await page.goto('/fr/dashboard/chat');
    const card = page.locator(CARD);
    await card.getByRole('button', { name: 'Confirmer' }).click();

    await expect(card.getByText("Cette demande n'est plus active.")).toBeVisible();
    await expect(card.getByRole('button')).toHaveCount(0);
  });

  test('a typed reply while the card is shown resolves it via_text', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(baseRoutes(PENDING_TOOL_CONFIRMATION, sseDone));

    await page.goto('/fr/dashboard/chat');
    const card = page.locator(CARD);
    await expect(card).toBeVisible();

    const textarea = page.locator('textarea');
    await textarea.fill('En fait, laisse tomber.');
    await textarea.press('Enter');

    // The via_text resolution is transient (badge visible while streaming,
    // component-tested); at done the card is cleared entirely.
    await expect(card).toHaveCount(0);
  });
});
