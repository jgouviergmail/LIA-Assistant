/**
 * Chat — the composer takes the document formats the instance publishes.
 *
 * Hermetic, in a real engine. The API publishes what an upload accepts
 * (`/config` → `attachments`); the picker offers those extensions, a document
 * picked is SENT — a Word file, and a Markdown file for which a browser reports
 * no type at all — and a format the instance does not publish is refused
 * before any request leaves. The unit tests mock the upload hook; only a
 * browser shows the whole door, from the picker to the request.
 */
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';

const APP_CONFIG = {
  sse: { heartbeat_interval_seconds: 15 },
  rate_limits: { enabled: false, per_minute: 60, burst: 10 },
  i18n: { supported_languages: ['fr', 'en'], default_language: 'fr' },
  features: { tool_approval_enabled: true, attachments_enabled: true },
  attachments: { image_types: ['image/png'], document_extensions: ['.docx', '.md', '.pdf'] },
  api_version: 'v1',
};

const CONVERSATION = {
  id: '00000000-0000-4000-8000-00000000f0a1',
  user_id: '00000000-0000-4000-8000-000000000001',
  title: 'E2E attachment formats',
  message_count: 0,
  total_tokens: 0,
  created_at: '2026-11-12T09:00:00Z',
  updated_at: '2026-11-12T09:00:00Z',
};

const WORD = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';

/** The file name of a multipart upload, read from its `Content-Disposition`. */
function uploadedName(body: string | null): string {
  return /filename="([^"]+)"/.exec(body ?? '')?.[1] ?? '';
}

function routes(uploads: string[]): MockRoute[] {
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
      url: '**/api/v1/attachments/upload',
      method: 'POST',
      handler: async route => {
        const name = uploadedName(route.request().postData());
        uploads.push(name);
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: `00000000-0000-4000-8000-0000000000${10 + uploads.length}`,
            original_filename: name,
            mime_type: name.endsWith('.md') ? 'text/markdown' : WORD,
            file_size: 2048,
            content_type: 'document',
            created_at: '2026-11-12T09:00:00Z',
          }),
        });
      },
    },
  ];
}

for (const width of [1280, 390]) {
  test(`at ${width}px: a Word and a Markdown document picked in the composer are uploaded`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await authenticate({ language: 'fr' });
    const uploads: string[] = [];
    await mockApi(routes(uploads));

    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);

    const picker = page.locator('input[type="file"][multiple]');
    // What the instance publishes is what the picker offers, by NAME.
    await expect(picker).toHaveAttribute('accept', 'image/*,.docx,.md,.pdf');

    await picker.setInputFiles({ name: 'notes.docx', mimeType: WORD, buffer: Buffer.from('PK') });
    await expect.poll(() => uploads).toEqual(['notes.docx']);
    await expect(page.getByText('notes.docx')).toBeVisible();

    // A browser reports no type for a Markdown file: its name is what is read.
    await picker.setInputFiles({ name: 'plan.md', mimeType: '', buffer: Buffer.from('# plan') });
    await expect.poll(() => uploads).toEqual(['notes.docx', 'plan.md']);
    await expect(page.getByText('plan.md')).toBeVisible();
  });
}

test('a format the instance does not publish is refused before any request leaves', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate({ language: 'fr' });
  const uploads: string[] = [];
  await mockApi(routes(uploads));

  await page.goto('/fr/dashboard/chat');
  await waitForHydration(page);

  await page.locator('input[type="file"][multiple]').setInputFiles({
    name: 'setup.exe',
    mimeType: 'application/x-msdownload',
    buffer: Buffer.from('MZ'),
  });

  await expect(page.getByText('Type de fichier non autorisé')).toBeVisible();
  expect(uploads).toEqual([]);
});
