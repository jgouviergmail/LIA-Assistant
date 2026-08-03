/**
 * What the share menu costs on a busy conversation.
 *
 * `ShareResponseMenu` renders on EVERY assistant bubble. Reading the settings
 * panel's `usePeerConnections` there — five queries, because that panel shows
 * requests, blocks and the access log too — cost 5 requests per message:
 * measured at 120 calls on a twelve-answer conversation, 80 % of them for data
 * the menu never reads.
 *
 * Only a browser can assert this: the defect is not in what renders, it is in
 * what LEAVES. Both halves matter — a closed menu must cost nothing, and an
 * opened one must still work.
 */
import { test, expect, type MockRoute } from '../fixtures';

const ANSWERS = 12;

const answer = (index: number) => ({
  id: `00000000-0000-4000-8000-0000000000m${index}`,
  role: 'assistant',
  content: `Réponse ${index}`,
  message_metadata: null,
  created_at: '2026-08-03T10:00:00Z',
  tokens_in: null,
  tokens_out: null,
  tokens_cache: null,
  cost_eur: null,
  google_api_requests: null,
  stt_provider: null,
});

const ROUTES: MockRoute[] = [
  {
    url: '**/api/v1/conversations/me',
    json: {
      id: '00000000-0000-4000-8000-00000000c001',
      user_id: '00000000-0000-4000-8000-000000000001',
      title: 'E2E',
      message_count: ANSWERS,
      total_tokens: 0,
      created_at: '2026-08-03T09:00:00Z',
      updated_at: '2026-08-03T10:00:00Z',
    },
  },
  {
    url: '**/api/v1/conversations/me/messages*',
    json: {
      messages: Array.from({ length: ANSWERS }, (_, index) => answer(index)),
      conversation_id: '00000000-0000-4000-8000-00000000c001',
      total_count: ANSWERS,
      has_more: false,
      next_cursor: null,
    },
  },
  { url: '**/api/v1/conversations/me/totals', json: {} },
  { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
  {
    url: '**/api/v1/peers/connections',
    json: [
      {
        id: 'c1',
        peer_id: 'p1',
        peer_display_name: 'Gérard Dupont',
        peer_email_hint: 'g***@example.com',
        peer_email: null,
        status: 'accepted',
        direction: null,
        requested_at: '2026-08-01T09:00:00Z',
        responded_at: '2026-08-01T09:05:00Z',
        context_message: null,
        my_shares: [],
        their_shares: [],
      },
    ],
  },
];

test.describe('share menu network cost', () => {
  test('a conversation nobody shares from costs no peer request at all', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const calls: string[] = [];
    page.on('request', request => {
      if (request.url().includes('/peers/')) calls.push(request.url());
    });

    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/chat');
    await expect(page.getByText('Réponse 0')).toBeVisible({ timeout: 25_000 });

    expect(calls, `a closed menu on ${ANSWERS} bubbles must cost nothing`).toHaveLength(0);
  });

  test('opening one menu fetches the recipients once, and they are usable', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const calls: string[] = [];
    page.on('request', request => {
      if (request.url().includes('/peers/connections')) calls.push(request.url());
    });

    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/chat');
    await expect(page.getByText('Réponse 0')).toBeVisible({ timeout: 25_000 });

    await page.getByRole('button', { name: "Plus d'actions" }).first().click();

    // The recipient appears — the lazy fetch must not cost the feature.
    await expect(page.getByRole('menuitem', { name: 'Gérard Dupont' })).toBeVisible({
      timeout: 10_000,
    });
    expect(calls, 'one open, one request').toHaveLength(1);
  });
});
