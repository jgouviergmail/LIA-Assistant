/**
 * Keeping an answer, and finding it again (ADR-282), in a real browser.
 *
 * Three things only a laid-out page proves, each a claim the feature makes:
 *
 * 1. **The bubble carries the toggle and the toggle asks the API.** The state
 *    is read ONCE for the chat; the first click POSTs the archived id, the
 *    icon fills, the second click DELETEs by that id. The oracle is what is
 *    ASKED, which survives a refactor of the gesture.
 * 2. **A bookmark detached from its conversation still reads whole** in the
 *    « Bookmarks » tab: the request quoted, the answer rendered with its
 *    formatting, and a delete that asks first then asks the server.
 * 3. **At 320 px no card reaches past the screen** — the gallery's oracle: the
 *    section clips, so the document never scrolls while a card overflows.
 */
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';

const ARCHIVED_ID = '00000000-0000-4000-8000-000000000001';
const BOOKMARK_ID = 'b1b2c3d4-0000-4000-8000-000000000009';

/** The instance offers bookmarks: the shell's config, with the flag on. */
const CONFIG: MockRoute = {
  url: '**/api/v1/config',
  json: {
    sse: { heartbeat_interval_seconds: 30 },
    rate_limits: { enabled: false, per_minute: 60, burst: 10 },
    i18n: { supported_languages: ['en', 'fr', 'de', 'es', 'it', 'zh'], default_language: 'en' },
    features: {
      workboard_enabled: true,
      tool_approval_enabled: false,
      attachments_enabled: true,
      rag_spaces_enabled: true,
      rag_spaces_embedding_model: 'text-embedding-3-small',
      bookmarks_enabled: true,
    },
    api_version: 'v1',
  },
};

function bookmark(overrides: Record<string, unknown> = {}) {
  return {
    id: BOOKMARK_ID,
    message_id: null,
    conversation_id: null,
    content: '**Réservé** : salle B, 14 h.\n\n- vidéoprojecteur\n- 6 places',
    request_content: 'Réserve la salle B à 14 h',
    answered_at: '2026-09-12T08:05:00Z',
    created_at: '2026-09-12T08:06:00Z',
    ...overrides,
  };
}

/** The chat with one archived answer, and the bookmark routes recording every ask. */
function chatRoutes(asked: string[]): MockRoute[] {
  return [
    CONFIG,
    { url: '**/api/v1/conversations/me/totals', json: {} },
    { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
    { url: '**/api/v1/agents/runs/active', json: { active: false } },
    { url: '**/api/v1/agents/hitl/pending', json: null },
    { url: '**/api/v1/usage/**', json: {} },
    {
      url: '**/api/v1/conversations/me/messages*',
      json: {
        messages: [
          {
            id: ARCHIVED_ID,
            role: 'assistant',
            content: 'Salle B réservée à 14 h.',
            created_at: '2026-09-12T08:05:00Z',
          },
        ],
        conversation_id: '00000000-0000-4000-8000-0000000000ff',
        total_count: 1,
        has_more: false,
        next_cursor: null,
      },
    },
    {
      url: '**/api/v1/bookmarks/state',
      handler: async route => {
        asked.push('GET state');
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ message_ids: {} }),
        });
      },
    },
    {
      url: /\/api\/v1\/bookmarks\/by-message\/[0-9a-f-]+$/,
      handler: async route => {
        asked.push(`DELETE ${route.request().url().split('/api/v1')[1]}`);
        await route.fulfill({ status: 204 });
      },
    },
    {
      url: /\/api\/v1\/bookmarks$/,
      method: 'POST',
      handler: async route => {
        const body = route.request().postDataJSON() as { message_id?: string };
        asked.push(`POST ${body.message_id ?? ''}`);
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(bookmark({ message_id: body.message_id })),
        });
      },
    },
  ];
}

/** The tab with one detached bookmark, recording the delete. */
function tabRoutes(asked: string[]): MockRoute[] {
  return [
    CONFIG,
    {
      url: /\/api\/v1\/bookmarks\/[0-9a-f-]+$/,
      method: 'DELETE',
      handler: async route => {
        asked.push(`DELETE ${route.request().url().split('/api/v1')[1]}`);
        await route.fulfill({ status: 204 });
      },
    },
    {
      url: /\/api\/v1\/bookmarks\?/,
      handler: async route => {
        asked.push(`GET ${new URL(route.request().url()).search}`);
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            items: [bookmark()],
            total: 1,
            limit: 24,
            offset: 0,
            max_limit: 100,
            max_per_user: 500,
          }),
        });
      },
    },
  ];
}

test.describe('message bookmarks', () => {
  test('the bubble keeps on the first click and lets go on the second', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    const asked: string[] = [];
    await mockApi(chatRoutes(asked));

    await page.goto('/fr/dashboard/chat');
    const toggle = page.getByTestId('bookmark-toggle');
    await waitForHydration(page, '[data-testid="bookmark-toggle"]');

    // ONE read of the state for the whole chat.
    await expect.poll(() => asked.filter(a => a === 'GET state').length).toBe(1);
    await expect(toggle).toHaveAttribute('aria-pressed', 'false');
    await expect(toggle).toHaveAccessibleName('Conserver cette réponse');

    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-pressed', 'true');
    await expect(toggle).toHaveAccessibleName('Retirer des bookmarks');
    expect(asked).toContain(`POST ${ARCHIVED_ID}`);

    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-pressed', 'false');
    expect(asked).toContain(`DELETE /bookmarks/by-message/${ARCHIVED_ID}`);
  });

  test('a detached bookmark reads whole in its tab, and delete asks the server', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    const asked: string[] = [];
    await mockApi(tabRoutes(asked));

    await page.goto('/fr/dashboard/settings?section=generated-assets&tab=bookmarks');
    await waitForHydration(page, '[data-testid="bookmark-card"]');

    // The tab opened straight from the URL, and asked for its first page.
    await expect(page.getByTestId('bookmarks-tab')).toHaveAttribute('aria-selected', 'true');
    expect(asked[0]).toMatch(/^GET \?limit=24/);

    const card = page.getByTestId('bookmark-card');
    await expect(card).toContainText('Réserve la salle B à 14 h');
    // The answer kept its formatting: bold rendered as bold, the list as a list.
    await expect(card.locator('strong', { hasText: 'Réservé' })).toBeVisible();
    await expect(card.locator('li', { hasText: 'vidéoprojecteur' })).toBeVisible();
    // The cap the account may reach is stated, from the payload.
    await expect(page.getByText('1 / 500 bookmarks')).toBeVisible();

    await card.getByRole('button', { name: 'Supprimer ce bookmark' }).click();
    await page.getByRole('alertdialog').getByRole('button', { name: /Supprimer/ }).click();

    await expect.poll(() => asked).toContain(`DELETE /bookmarks/${BOOKMARK_ID}`);
  });

  test('at 320 px no card reaches past the screen', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'fr' });
    await page.setViewportSize({ width: 320, height: 720 });
    await mockApi(tabRoutes([]));

    await page.goto('/fr/dashboard/settings?section=generated-assets&tab=bookmarks');
    await waitForHydration(page, '[data-testid="bookmark-card"]');

    const box = await page.getByTestId('bookmark-card').boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x + box!.width).toBeLessThanOrEqual(320);
  });
});
