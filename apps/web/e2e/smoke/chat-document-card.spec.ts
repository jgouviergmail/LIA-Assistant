/**
 * Chat journey — generated document cards (ADR-226).
 *
 * Hermetic: the conversation history is mocked with one assistant message
 * carrying two `generated_documents` entries (csv + pdf) in its metadata,
 * everything else dies on the 501 catch-all. Proves, in a real browser
 * accessibility tree, that each card exposes a NAMED native link — the csv
 * as a download (`download` attribute), the pdf opening in a new tab (the
 * API serves application/pdf inline) — and that the link is keyboard
 * reachable.
 */
import { test, expect, type MockRoute } from '../fixtures';

const assistantMessage = {
  id: '00000000-0000-4000-8000-00000000m001',
  role: 'assistant',
  content: 'Voici votre document.',
  message_metadata: {
    generated_documents: [
      {
        url: '/api/v1/attachments/00000000-0000-4000-8000-00000000d001',
        filename: 'modeles-llm.csv',
        doc_type: 'csv',
        size_bytes: 2048,
        expires_at: null,
      },
      {
        url: '/api/v1/attachments/00000000-0000-4000-8000-00000000d002',
        filename: 'rapport.pdf',
        doc_type: 'pdf',
        size_bytes: 40960,
        expires_at: null,
      },
    ],
  },
  created_at: '2026-08-17T10:00:00Z',
  tokens_in: null,
  tokens_out: null,
  tokens_cache: null,
  cost_eur: null,
  google_api_requests: null,
  stt_provider: null,
};

const chatData: MockRoute[] = [
  {
    url: '**/api/v1/conversations/me',
    json: {
      id: '00000000-0000-4000-8000-00000000c001',
      user_id: '00000000-0000-4000-8000-000000000001',
      title: 'E2E',
      message_count: 1,
      total_tokens: 0,
      created_at: '2026-08-17T09:00:00Z',
      updated_at: '2026-08-17T10:00:00Z',
    },
  },
  {
    url: '**/api/v1/conversations/me/messages*',
    json: {
      messages: [assistantMessage],
      conversation_id: '00000000-0000-4000-8000-00000000c001',
      total_count: 1,
      has_more: false,
      next_cursor: null,
    },
  },
  { url: '**/api/v1/conversations/me/totals', json: {} },
  {
    url: '**/api/v1/agents/health',
    json: { status: 'healthy', graph_compiled: true },
  },
];

test.describe('chat generated document cards', () => {
  test('cards expose named, keyboard-reachable links (download vs open-in-tab)', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(chatData);

    await page.goto('/en/dashboard/chat');

    // Both cards render with their filenames visible.
    await expect(page.getByText('modeles-llm.csv')).toBeVisible();
    await expect(page.getByText('rapport.pdf')).toBeVisible();
    await expect(page.getByTestId('generated-document-card')).toHaveCount(2);

    // The csv action is a NAMED native link that downloads the file.
    const download = page.getByRole('link', { name: 'Download modeles-llm.csv' });
    await expect(download).toBeVisible();
    await expect(download).toHaveAttribute(
      'href',
      '/api/v1/attachments/00000000-0000-4000-8000-00000000d001'
    );
    await expect(download).toHaveAttribute('download', 'modeles-llm.csv');

    // The pdf action opens in a new tab (served inline by the API).
    const open = page.getByRole('link', { name: 'Open rapport.pdf' });
    await expect(open).toBeVisible();
    await expect(open).toHaveAttribute('target', '_blank');

    // Keyboard reachability: the link takes focus like any native anchor.
    await download.focus();
    await expect(download).toBeFocused();
  });
});
