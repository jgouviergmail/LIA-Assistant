/**
 * Chat journey — connector error notice banner (Lot 3 P3, ADR-134).
 *
 * Hermetic: the POST /agents/chat/stream response is a mocked SSE body
 * carrying a `tool_error` execution step (shape from the 2026-07-18 runtime
 * capture), everything else dies on the 501 catch-all. Proves in a real
 * browser accessibility tree that:
 *   - a reconnect tool_error renders the amber banner with the human
 *     connector label and a "Reconnecter" link to the connectors settings;
 *   - dismiss (✕) removes the banner;
 *   - sending a new message clears the banner (fresh verdict per turn).
 *
 * No backend, LLM, or paid provider is contacted.
 */
import { test, expect, type MockRoute } from '../fixtures';

const CONVERSATION = {
  id: '00000000-0000-4000-8000-00000000c002',
  user_id: '00000000-0000-4000-8000-000000000001',
  title: 'E2E connector notice',
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

/** SSE body: a tool_error step (runtime capture shape) then a plain answer. */
function sseToolError(): string {
  return (
    'data: {"type":"execution_step","content":"","metadata":{"connector_type":"google_gmail",' +
    '"action":"reconnect","tool_name":"get_emails_tool","step_type":"tool_error"}}\n\n' +
    'data: {"type":"token","content":"Je ne peux pas accéder à vos e-mails."}\n\n' +
    'data: {"type":"done","content":"","metadata":null}\n\n'
  );
}

function baseRoutes(): MockRoute[] {
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
    { url: '**/api/v1/agents/hitl/pending', json: null },
    { url: '**/api/v1/usage/**', json: {} },
    {
      url: '**/api/v1/agents/chat/stream',
      method: 'POST',
      handler: async route => {
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body: sseToolError(),
        });
      },
    },
  ];
}

async function sendMessage(page: import('@playwright/test').Page, text: string): Promise<void> {
  const textarea = page.locator('textarea');
  await textarea.fill(text);
  await textarea.press('Enter');
}

test.describe('chat connector error notice', () => {
  test('reconnect tool_error renders the banner with label and settings link', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(baseRoutes());

    await page.goto('/fr/dashboard/chat');
    await sendMessage(page, 'Cherche mes emails');

    // Human label (Gmail) resolved client-side from connector_type.
    await expect(page.getByText(/Gmail/).first()).toBeVisible();
    const link = page.getByRole('link', { name: 'Reconnecter' });
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute('href', '/fr/dashboard/settings?section=connectors');
  });

  test('dismiss removes the banner', async ({ page, authenticate, mockApi }) => {
    await authenticate();
    await mockApi(baseRoutes());

    await page.goto('/fr/dashboard/chat');
    await sendMessage(page, 'Cherche mes emails');

    const link = page.getByRole('link', { name: 'Reconnecter' });
    await expect(link).toBeVisible();

    await page.getByRole('button', { name: "Fermer l'avertissement" }).click();
    await expect(link).not.toBeVisible();
  });

  test('a new message clears the banner (fresh verdict per turn)', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(baseRoutes());

    await page.goto('/fr/dashboard/chat');
    await sendMessage(page, 'Cherche mes emails');

    const link = page.getByRole('link', { name: 'Reconnecter' });
    await expect(link).toBeVisible();

    // The mocked stream re-emits the tool_error on the second turn too, so
    // assert the transient clear: right after send, before the SSE chunk
    // lands again, the banner must have been reset by SEND_MESSAGE. The
    // reliable observable is that it is visible again AFTER the second turn
    // (ADD ran on a cleared list — count stays 1, never 2).
    await sendMessage(page, 'Cherche encore');
    await expect(page.getByRole('link', { name: 'Reconnecter' })).toHaveCount(1);
  });
});
