/**
 * Chat journey — header layout: left-aligned search + status pill.
 *
 * Hermetic (mocked API, no backend/LLM). Pins the product-requested
 * arrangement (2026-07-22):
 *   - the message-search field sits in the LEFT half of the header;
 *   - the nominal "online" state shows NO status pill (QW-12 silence);
 *   - when the API is offline, the "Hors ligne" pill appears LEFT of the
 *     search field.
 */
import { test, expect, type MockRoute } from '../fixtures';

const CONVERSATION = {
  id: '00000000-0000-4000-8000-00000000c003',
  user_id: '00000000-0000-4000-8000-000000000001',
  title: 'E2E header layout',
  message_count: 0,
  total_tokens: 0,
  created_at: '2026-07-22T09:00:00Z',
  updated_at: '2026-07-22T10:00:00Z',
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

function baseRoutes(healthy: boolean): MockRoute[] {
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
    healthy
      ? { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } }
      : {
          url: '**/api/v1/agents/health',
          handler: async route => {
            await route.fulfill({ status: 503, json: { status: 'unhealthy' } });
          },
        },
    { url: '**/api/v1/agents/runs/active', json: { active: false } },
    { url: '**/api/v1/agents/hitl/pending', json: null },
    { url: '**/api/v1/usage/**', json: {} },
  ];
}

test.describe('chat header layout', () => {
  test('search field is left-aligned and no status pill shows when online', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(baseRoutes(true));

    await page.goto('/fr/dashboard/chat');

    const search = page.getByRole('searchbox', { name: 'Rechercher...' });
    await expect(search).toBeVisible();

    // Nominal state: silent — no offline pill.
    await expect(page.getByText('Hors ligne')).not.toBeVisible();

    // The search field sits in the LEFT half of the viewport.
    const box = await search.boundingBox();
    const viewport = page.viewportSize();
    expect(box).not.toBeNull();
    expect(viewport).not.toBeNull();
    expect(box!.x + box!.width / 2).toBeLessThan(viewport!.width / 2);
  });

  test('offline pill appears LEFT of the search field when the API is down', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(baseRoutes(false));

    await page.goto('/fr/dashboard/chat');

    const pill = page.getByText('Hors ligne');
    await expect(pill).toBeVisible();
    const search = page.getByRole('searchbox', { name: 'Rechercher...' });
    await expect(search).toBeVisible();

    const pillBox = await pill.boundingBox();
    const searchBox = await search.boundingBox();
    expect(pillBox).not.toBeNull();
    expect(searchBox).not.toBeNull();
    // Pill strictly left of the search field, on the same header row.
    expect(pillBox!.x + pillBox!.width).toBeLessThanOrEqual(searchBox!.x);
  });
});
