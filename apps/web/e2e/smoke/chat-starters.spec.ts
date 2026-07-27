/**
 * Empty-chat starters (W8) — the first screen offers a way in.
 *
 * An empty conversation showed a greeting, a description and nothing to act on:
 * the one screen where a newcomer has the least idea what to type. Three
 * starters now sit under the hero, chosen so they resolve on ANY account —
 * connected or not — because suggesting "show my last emails" to someone with
 * no mail connector turns the first interaction into a failure.
 *
 * What only a browser can prove: the click lands the phrase in the real
 * composer, nothing is sent, and the starters disappear once the conversation
 * has content instead of lingering as beginner furniture.
 */
import { test, expect, type MockRoute } from '../fixtures';

const EMPTY_CHAT: MockRoute[] = [
  {
    url: '**/api/v1/conversations/me/messages*',
    json: {
      messages: [],
      conversation_id: null,
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
];

test.describe('starters on an empty chat', () => {
  test('a starter prefills the composer without sending', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });

    // Any call to the streaming endpoint breaks the contract.
    let sent = 0;
    await page.route('**/api/v1/agents/chat/stream**', route => {
      sent += 1;
      return route.fulfill({ status: 200, body: '' });
    });
    await mockApi(EMPTY_CHAT);
    await page.goto('/fr/dashboard/chat');

    const starters = page.getByRole('group', { name: /Essayez par exemple/ });
    await expect(starters).toBeVisible({ timeout: 30_000 });

    const first = starters.getByRole('button').first();
    const phrase = (await first.textContent())?.trim() ?? '';
    expect(phrase.length, 'a starter must carry a real phrase').toBeGreaterThan(3);
    // A translation key leaking through would be sent verbatim to the model.
    expect(phrase).not.toContain('chat.starters');

    await first.click();

    const composer = page.getByRole('textbox').first();
    await expect(composer).toHaveValue(phrase, { timeout: 15_000 });

    // Give a spurious auto-send time to happen before concluding it does not.
    await page.waitForTimeout(1_000);
    expect(sent, 'a starter must never send on its own').toBe(0);
  });

  test('starters make way once the conversation has content', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // Beginner scaffolding must not survive into a real conversation.
    await authenticate({ language: 'fr' });
    await mockApi([
      {
        url: '**/api/v1/conversations/me/messages*',
        json: {
          messages: [
            {
              id: 'm1',
              role: 'user',
              content: 'Bonjour',
              created_at: '2026-07-26T08:00:00Z',
              message_metadata: null,
            },
            {
              id: 'm2',
              role: 'assistant',
              content: 'Bonjour ! Comment puis-je aider ?',
              created_at: '2026-07-26T08:00:05Z',
              message_metadata: null,
            },
          ],
          conversation_id: 'c1',
          total_count: 2,
          has_more: false,
          next_cursor: null,
        },
      },
      ...EMPTY_CHAT.slice(1),
    ]);
    await page.goto('/fr/dashboard/chat');

    await expect(page.getByText('Comment puis-je aider ?')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole('group', { name: /Essayez par exemple/ })).toHaveCount(0);
  });
});
