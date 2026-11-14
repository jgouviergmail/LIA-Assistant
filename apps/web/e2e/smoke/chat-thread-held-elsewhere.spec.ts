/**
 * Chat journey — a message sent while LIA works on the thread elsewhere (point 25b).
 *
 * Hermetic: the chat POST answers the API's 409 for a run that relays no
 * chunk — a ticket or a voice relay holds the account, and `public_active_run`
 * names no stream for it. Before the first fix the 409 named the run's stream:
 * the page announced a resume, followed a stream nobody writes, and failed only
 * once its watchdog gave up. Since ADR-384 the page refuses nothing either: the
 * words wait their turn, kept by the server, and the page says so at once —
 * still following nothing, since there is nothing to follow.
 */
import { test, expect, chatRoutes, waitForHydration } from '../fixtures';
import type { WaitingMessage } from '@/lib/waiting-message';

const QUEUED = 'LIA is busy: your message waits its turn.';
const REFUSED =
  'LIA is already working on this conversation. Your message was not sent — try again in a moment.';
const RESUMING = 'Reattaching to the response in progress…';
const WORDS = 'What is on my calendar today?';
const NOW = '2026-11-14T09:00:00Z';

interface KeptWords {
  message?: string;
  behind_stream_id?: string | null;
}

test.describe('chat thread held by a ticket or a call (point 25b)', () => {
  test('a message sent meanwhile waits its turn, and nothing is followed', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const sent: unknown[] = [];
    const kept: KeptWords[] = [];
    const followed: string[] = [];
    let waiting: WaitingMessage | null = null;
    await authenticate();
    await mockApi(chatRoutes([]));
    // Registered after the shared chat routes, so these win (routes are LIFO).
    await mockApi([
      {
        url: '**/api/v1/agents/chat/stream',
        method: 'POST',
        handler: async route => {
          sent.push(route.request().postDataJSON());
          await route.fulfill({
            status: 409,
            contentType: 'application/json',
            body: JSON.stringify({
              detail: {
                error: 'run_in_progress',
                active_run: { run_id: 'ticket-run-1', stream_id: null },
              },
            }),
          });
        },
      },
      {
        // The waiting message's door: it keeps the words the busy account refused.
        url: '**/api/v1/agents/chat/waiting*',
        handler: async route => {
          if (route.request().method() === 'POST') {
            const body = (route.request().postDataJSON() ?? {}) as KeptWords;
            kept.push(body);
            waiting = {
              conversation_id: '00000000-0000-4000-8000-0000000000ff',
              conversation_revision: 0,
              content: String(body.message),
              status: 'waiting',
              version: 1,
              send_requested: false,
              stream_id: null,
              can_join: false,
              created_at: NOW,
              updated_at: NOW,
            };
            await route.fulfill({
              status: 200,
              json: { waiting, departed: false, stream_id: null },
            });
            return;
          }
          // Nothing waiting is the JSON `null`, typed as the API types it.
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(waiting),
          });
        },
      },
      {
        url: '**/api/v1/agents/runs/*/stream',
        handler: async route => {
          followed.push(route.request().url());
          await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' });
        },
      },
    ]);

    await page.goto('/en/dashboard/chat');
    await waitForHydration(page);
    const composer = page.locator('textarea[data-chat-composer]');
    await composer.fill(WORDS);
    await composer.press('Enter');

    await expect.poll(() => sent.length, { timeout: 30_000 }).toBe(1);
    // Neither lost nor refused: the server keeps the words, behind no stream.
    await expect.poll(() => kept.length, { timeout: 30_000 }).toBe(1);
    expect(kept[0].message).toBe(WORDS);
    expect(kept[0].behind_stream_id ?? null).toBeNull();
    await expect(page.getByText(QUEUED)).toBeVisible();
    await expect(page.getByRole('group', { name: 'Waiting message' })).toContainText(WORDS);
    await expect(page.getByText(REFUSED)).toHaveCount(0);
    await expect(page.getByText(RESUMING)).toHaveCount(0);
    expect(followed).toHaveLength(0);
  });
});
