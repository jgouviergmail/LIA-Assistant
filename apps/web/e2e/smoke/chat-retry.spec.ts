/**
 * Retry after a failure (W3) — the dead end has an exit.
 *
 * A failed turn ended as an anonymous assistant bubble carrying the localized
 * error text. Nothing marked it, nothing offered a way back: the user had to
 * scroll up, find their question and retype it. On the one surface where the
 * product's whole value is a single exchange, the failure path had no recovery.
 *
 * This proves the full loop in a real browser: send → the stream fails → the
 * error bubble offers a retry → pressing it replays the EXACT prompt through
 * the normal send path → the second attempt succeeds.
 */
import { test, expect, type MockRoute } from '../fixtures';

const QUESTION = 'Quelle est la météo demain ?';

const BASE: MockRoute[] = [
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

/** SSE body: a typed error, then the terminating done chunk. */
function sseError(): string {
  return (
    'data: {"type":"error","content":"La connexion a été perdue.","metadata":null}\n\n' +
    'data: {"type":"done","content":"","metadata":null}\n\n'
  );
}

/** SSE body: a normal short answer. */
function sseAnswer(): string {
  return (
    'data: {"type":"token","content":"Grand soleil.","metadata":null}\n\n' +
    'data: {"type":"done","content":"","metadata":null}\n\n'
  );
}

test.describe('retry after a failed turn', () => {
  test('the error offers a retry that replays the exact prompt', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });

    // First stream fails, second succeeds — and the second request body is
    // captured so we can assert WHAT was replayed, not merely that something was.
    const sentPrompts: string[] = [];
    let attempt = 0;
    await mockApi([
      ...BASE,
      {
        url: '**/api/v1/agents/chat/stream',
        method: 'POST',
        handler: async route => {
          const body = route.request().postDataJSON() as { message?: string } | null;
          if (body?.message) sentPrompts.push(body.message);
          attempt += 1;
          await route.fulfill({
            status: 200,
            contentType: 'text/event-stream',
            body: attempt === 1 ? sseError() : sseAnswer(),
          });
        },
      },
    ]);

    await page.goto('/fr/dashboard/chat');
    const composer = page.locator('textarea').first();
    await composer.waitFor({ state: 'visible' });

    await composer.fill(QUESTION);
    await composer.press('Enter');

    // The failure surfaces…
    await expect(page.getByText('La connexion a été perdue.')).toBeVisible();

    // …and it is no longer a dead end.
    const retry = page.getByRole('button', { name: 'Réessayer' });
    await expect(retry).toBeVisible();
    await retry.click();

    await expect(page.getByText('Grand soleil.')).toBeVisible();

    // The replay carried the original question, verbatim.
    expect(sentPrompts).toEqual([QUESTION, QUESTION]);

    // Once the conversation has moved on, the stale failure stops offering a
    // retry — replaying it would drop the question into a changed context.
    await expect(page.getByRole('button', { name: 'Réessayer' })).toHaveCount(0);
  });

  test('a successful turn offers no retry', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'fr' });
    await mockApi([
      ...BASE,
      {
        url: '**/api/v1/agents/chat/stream',
        method: 'POST',
        handler: async route => {
          await route.fulfill({
            status: 200,
            contentType: 'text/event-stream',
            body: sseAnswer(),
          });
        },
      },
    ]);

    await page.goto('/fr/dashboard/chat');
    const composer = page.locator('textarea').first();
    await composer.waitFor({ state: 'visible' });
    await composer.fill('Bonjour');
    await composer.press('Enter');

    await expect(page.getByText('Grand soleil.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Réessayer' })).toHaveCount(0);
  });
});
