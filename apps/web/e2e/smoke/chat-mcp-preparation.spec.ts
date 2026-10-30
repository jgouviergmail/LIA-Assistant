/**
 * Chat journey — a slow personal MCP server is announced while the turn waits (spec 2026-10-21 §5.6).
 *
 * Hermetic: POST /agents/chat/stream answers a mocked SSE body with the
 * preparation chunks the backend streams before the graph — the generic
 * progress step, then « slow » and the terminal phase of each slow server —
 * followed by a plain answer. Proves in a real browser that:
 *   - a slow server raises a polite, closable toast naming it, and the
 *     toast never takes the focus;
 *   - a server left out at the ceiling turns that toast into the « not used
 *     for this message » notice instead of stacking a second one;
 *   - past three slow servers, the ONE grouped notice still names the server
 *     it left out, in the language's own quotes;
 *   - the answer still arrives.
 *
 * No backend, LLM, or paid provider is contacted.
 */
import { test, expect, type MockRoute } from '../fixtures';

const CONVERSATION = {
  id: '00000000-0000-4000-8000-00000000c0a1',
  user_id: '00000000-0000-4000-8000-000000000001',
  title: 'E2E MCP preparation',
  message_count: 0,
  total_tokens: 0,
  created_at: '2026-10-28T09:00:00Z',
  updated_at: '2026-10-28T10:00:00Z',
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

function step(metadata: Record<string, unknown>): string {
  return `data: ${JSON.stringify({ type: 'execution_step', content: '', metadata })}\n\n`;
}

function notice(
  key: string,
  phase: string,
  elapsedMs: number,
  server = { id: '0b6c2f1e-0000-4000-8000-000000000001', name: 'Carnet de notes' }
): string {
  return step({
    step_type: 'mcp_preparation',
    i18n_key: key,
    emoji: null,
    server_key: server.id,
    server_name: server.name,
    phase,
    elapsed_ms: elapsedMs,
  });
}

const FIVE_SERVERS = ['Agenda', 'Banque', 'Cuisine', 'Dépôt', 'Carnet de notes'].map(
  (name, index) => ({ id: `0b6c2f1e-0000-4000-8000-00000000010${index}`, name })
);

/** Five slow servers (one grouped notice); four get ready, the last is left out. */
function sseGroupWithOneLeftOut(): string {
  const slow = FIVE_SERVERS.map(server =>
    notice('chat.mcp_preparation.slow', 'slow', 10_000, server)
  ).join('');
  const ready = FIVE_SERVERS.slice(0, 4)
    .map(server => notice('chat.mcp_preparation.ready', 'ready', 12_000, server))
    .join('');
  return (
    slow +
    ready +
    notice('chat.mcp_preparation.deferred', 'deferred', 20_000, FIVE_SERVERS[4]) +
    'data: {"type":"token","content":"Voici ce que je peux faire sans tes notes."}\n\n' +
    'data: {"type":"done","content":"","metadata":null}\n\n'
  );
}

/** The preparation, slow then left out at the ceiling, then an answer without its tools. */
function sseSlowThenDeferred(): string {
  return (
    step({
      step_type: 'mcp_preparation',
      i18n_key: 'mcp_preparation',
      emoji: '🧩',
      server_key: null,
      server_name: null,
      phase: 'discovering',
      elapsed_ms: 0,
    }) +
    notice('chat.mcp_preparation.slow', 'slow', 10_000) +
    notice('chat.mcp_preparation.deferred', 'deferred', 20_000) +
    'data: {"type":"token","content":"Voici ce que je peux faire sans tes notes."}\n\n' +
    'data: {"type":"done","content":"","metadata":null}\n\n'
  );
}

function sseSlowOnly(): string {
  return notice('chat.mcp_preparation.slow', 'slow', 10_000);
}

function baseRoutes(body: () => string): MockRoute[] {
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
        await route.fulfill({ status: 200, contentType: 'text/event-stream', body: body() });
      },
    },
  ];
}

async function sendMessage(page: import('@playwright/test').Page, text: string): Promise<void> {
  const textarea = page.locator('textarea');
  await textarea.fill(text);
  await textarea.press('Enter');
}

test.describe('chat MCP preparation notices', () => {
  test('a slow server is announced politely, closable, without taking the focus', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(baseRoutes(sseSlowOnly));

    await page.goto('/fr/dashboard/chat');
    await sendMessage(page, 'Résume mes notes');

    const toastItem = page.locator('[data-sonner-toast]').filter({
      hasText: 'Carnet de notes',
    });
    await expect(toastItem).toContainText('met du temps à se préparer');
    await expect(page.locator('[aria-live="polite"]').filter({ has: toastItem })).toHaveCount(1);
    await expect(toastItem.getByRole('button', { name: 'Fermer' })).toBeVisible();
    // A polite notice never takes the focus: whatever holds it, it is not in the toaster.
    expect(
      await page.evaluate(() => Boolean(document.activeElement?.closest('[data-sonner-toaster]')))
    ).toBe(false);
  });

  test('a server left out at the ceiling turns its toast into the outcome', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(baseRoutes(sseSlowThenDeferred));

    await page.goto('/fr/dashboard/chat');
    await sendMessage(page, 'Résume mes notes');

    await expect(page.getByText('Voici ce que je peux faire sans tes notes.')).toBeVisible();
    const toasts = page.locator('[data-sonner-toast]').filter({ hasText: 'Carnet de notes' });
    await expect(toasts).toHaveCount(1);
    await expect(toasts).toContainText('n’a pas répondu à temps');
  });

  test('a grouped notice names the server it left out', async ({ page, authenticate, mockApi }) => {
    await authenticate();
    await mockApi(baseRoutes(sseGroupWithOneLeftOut));

    await page.goto('/fr/dashboard/chat');
    await sendMessage(page, 'Résume mes notes');

    await expect(page.getByText('Voici ce que je peux faire sans tes notes.')).toBeVisible();
    const group = page
      .locator('[data-sonner-toast]')
      .filter({ hasText: 'n’a pas répondu à temps' });
    await expect(group).toHaveCount(1);
    // « 1 serveur MCP (« Carnet de notes ») … » — the name sits in its isolate marks.
    await expect(group).toContainText('1 serveur MCP');
    await expect(group).toContainText('Carnet de notes');
    await expect(group).not.toContainText('Agenda');
  });
});
