/**
 * Chat journey — a message sent while LIA works on the thread elsewhere (point 25b).
 *
 * Hermetic: the chat POST answers the API's 409 for a run that relays no
 * chunk — a ticket or a voice relay holds the conversation's lock, and
 * `public_active_run` names no stream for it. Before the fix the 409 named
 * the run's stream: the page announced a resume, followed a stream nobody
 * writes, and failed only once its watchdog gave up. The page now follows
 * nothing and says at once what happened: LIA is busy, the message was not
 * sent. The busy message used to claim a reattachment it never made.
 */
import { test, expect, chatRoutes, waitForHydration } from '../fixtures';

const BUSY =
  'LIA is already working on this conversation. Your message was not sent — try again in a moment.';
const RESUMING = 'Reattaching to the response in progress…';

test.describe('chat thread held by a ticket or a call (point 25b)', () => {
  test('a message sent meanwhile is refused plainly, and nothing is followed', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const sent: unknown[] = [];
    const followed: string[] = [];
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
        url: '**/api/v1/agents/runs/*/stream',
        handler: async route => {
          followed.push(route.request().url());
          await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' });
        },
      },
    ]);

    await page.goto('/en/dashboard/chat');
    await waitForHydration(page);
    const composer = page.locator('textarea');
    await composer.fill('What is on my calendar today?');
    await composer.press('Enter');

    await expect.poll(() => sent.length, { timeout: 30_000 }).toBe(1);
    await expect(page.getByText(BUSY)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(RESUMING)).toHaveCount(0);
    expect(followed).toHaveLength(0);
  });
});
