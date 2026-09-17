/**
 * Chat — the « + » attaches a document of a knowledge space, paused or not.
 *
 * Hermetic, in a real engine: with the spaces on, the composer's « + » opens
 * a menu; its knowledge entry lists the person's indexed documents with the
 * space named beside each (a paused one badged); a pick posts the copy
 * endpoint, the copy joins the strip like an upload, and the message leaves
 * with that attachment id. Desktop and 390 px.
 */
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';

const NL = String.fromCharCode(10);

const APP_CONFIG = {
  sse: { heartbeat_interval_seconds: 15 },
  rate_limits: { enabled: false, per_minute: 60, burst: 10 },
  i18n: { supported_languages: ['fr', 'en'], default_language: 'fr' },
  features: {
    tool_approval_enabled: true,
    attachments_enabled: true,
    rag_spaces_enabled: true,
    rag_spaces_embedding_model: 'e',
  },
  api_version: 'v1',
};

const CONVERSATION = {
  id: '00000000-0000-4000-8000-00000000c0a1',
  user_id: '00000000-0000-4000-8000-000000000001',
  title: 'E2E knowledge attachment',
  message_count: 0,
  total_tokens: 0,
  created_at: '2026-09-17T09:00:00Z',
  updated_at: '2026-09-17T09:00:00Z',
};

const LISTING = {
  items: [
    {
      id: '00000000-0000-4000-8000-0000000000d1',
      space_id: '00000000-0000-4000-8000-0000000000a1',
      space_name: 'Contrats',
      space_is_active: true,
      original_filename: 'bail 2026.pdf',
      content_type: 'application/pdf',
      file_size: 20480,
      created_at: '2026-09-10T09:00:00Z',
    },
    {
      id: '00000000-0000-4000-8000-0000000000d2',
      space_id: '00000000-0000-4000-8000-0000000000a2',
      space_name: 'Archives',
      space_is_active: false,
      original_filename: 'ancien bail 2019.pdf',
      content_type: 'application/pdf',
      file_size: 10240,
      created_at: '2026-08-01T09:00:00Z',
    },
  ],
  total: 2,
  limit: 50,
  offset: 0,
  max_limit: 100,
};

const COPY_ID = '00000000-0000-4000-8000-0000000000e1';

function routes(copies: unknown[], bodies: Record<string, unknown>[]): MockRoute[] {
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
    { url: '**/api/v1/rag-spaces/documents*', json: LISTING },
    {
      url: '**/api/v1/attachments/from-knowledge-document',
      method: 'POST',
      handler: async route => {
        copies.push(route.request().postDataJSON());
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: COPY_ID,
            original_filename: 'ancien bail 2019.pdf',
            mime_type: 'application/pdf',
            file_size: 10240,
            content_type: 'document',
            created_at: '2026-09-17T09:00:00Z',
          }),
        });
      },
    },
    {
      url: '**/api/v1/agents/chat/stream',
      method: 'POST',
      handler: async route => {
        bodies.push((route.request().postDataJSON() ?? {}) as Record<string, unknown>);
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body:
            'data: {"type":"token","content":"Le bail court jusqu’en 2029."}' +
            NL +
            NL +
            'data: {"type":"done","content":"","metadata":null}' +
            NL +
            NL,
        });
      },
    },
  ];
}

async function attachThePausedSpaceDocument(
  page: import('@playwright/test').Page
): Promise<void> {
  // Opened from the keyboard: on a phone-wide dev server the Next.js dev
  // overlay badge sits over the composer's bottom-left corner and swallows a
  // pointer click; the keyboard path is the one every user of the menu has.
  const plus = page.getByRole('button', { name: 'Joindre un fichier' });
  await expect(plus).toBeEnabled();
  await plus.focus();
  await page.keyboard.press('Enter');
  const menu = page.getByRole('menu');
  await expect(menu).toBeVisible();
  await menu.getByRole('menuitem', { name: /espace de connaissances/ }).click();

  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText('bail 2026.pdf')).toBeVisible();
  const paused = dialog.locator('li', { hasText: 'ancien bail 2019.pdf' });
  await expect(paused).toContainText('Archives');
  await expect(paused).toContainText('espace en pause');
  await paused.getByRole('checkbox').check();
  await dialog.getByRole('button', { name: /^Joindre 1 document$/ }).click();
  await expect(dialog).toBeHidden();
}

for (const width of [1280, 390]) {
  test(`at ${width}px: the « + » offers a paused space's document, the message leaves with its copy`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await authenticate({ language: 'fr' });
    const copies: unknown[] = [];
    const bodies: Record<string, unknown>[] = [];
    await mockApi(routes(copies, bodies));

    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);

    await attachThePausedSpaceDocument(page);

    // The copy was asked of the API with the space AND the document.
    expect(copies).toEqual([
      { space_id: LISTING.items[1].space_id, document_id: LISTING.items[1].id },
    ]);
    // The copy sits in the strip like an upload would.
    await expect(page.getByText('ancien bail 2019.pdf')).toBeVisible();

    await page.locator('textarea').fill('Jusqu’à quand court ce bail ?');
    await page.keyboard.press('Enter');
    await expect.poll(() => bodies.length).toBe(1);
    expect(bodies[0].attachment_ids).toEqual([COPY_ID]);
    await expect(page.getByText(/2029/)).toBeVisible({ timeout: 15_000 });
  });
}
