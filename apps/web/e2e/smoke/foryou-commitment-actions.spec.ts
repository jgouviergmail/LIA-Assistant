/**
 * Closing a commitment from the "For you" card.
 *
 * The card renders the BRIEFING section, not the ledger's own list — so the
 * hook's optimistic removal is invisible here. Shipped without an explicit
 * reload, the closed row stayed on screen and the next click landed on a
 * commitment the API had already closed: `404 Open_loop not found`.
 *
 * Only a browser proves the sequence, because it is about what the SERVER is
 * asked twice: this spec counts the close requests and their ids.
 */
import { test, expect, type MockRoute } from '../fixtures';

const LOOP_ID = '772c69f3-e308-408b-84c5-ff654d939eb5';

function cards(withLoop: boolean) {
  const empty = {
    status: 'empty',
    data: null,
    generated_at: '2026-08-03T08:00:00Z',
    error_code: null,
    error_message: null,
  };
  return {
    cards: {
      weather: empty,
      agenda: empty,
      mails: empty,
      birthdays: empty,
      health: empty,
      tasks: empty,
      documents: empty,
      reminders: empty,
      for_you: withLoop
        ? {
            status: 'ok',
            data: {
              open_loops: [
                {
                  id: LOOP_ID,
                  subject: 'Rendre la perceuse',
                  counterparty: null,
                  direction: 'user_owes',
                  due_hint: null,
                  days_open: 4,
                },
              ],
              recent_automations: [],
              next_automation: null,
            },
            generated_at: '2026-08-03T08:00:00Z',
            error_code: null,
            error_message: null,
          }
        : empty,
    },
  };
}

test('a closed commitment leaves the card instead of 404-ing on the next click', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const closes: string[] = [];
  page.on('request', request => {
    if (request.url().includes('/close')) closes.push(request.url());
  });

  // The section answers WITH the loop until it is closed, and without it
  // after — exactly what the server does once the card asks again.
  let closed = false;
  const routes: MockRoute[] = [
    {
      url: '**/api/v1/briefing/synthesis',
      json: { greeting: { text: 'Bonjour', generated_at: null, usage: null }, synthesis: null },
    },
    { url: '**/api/v1/usage/**', json: {} },
    { url: `**/api/v1/open-loops/${LOOP_ID}/close`, method: 'POST', json: { id: LOOP_ID } },
  ];
  await authenticate({ language: 'fr' });
  await mockApi(routes);
  await page.route('**/api/v1/briefing/cards**', route =>
    route.fulfill({ json: cards(!closed) })
  );
  // `onRefresh` force-refreshes the section through POST /briefing/refresh-cards,
  // not by re-reading /briefing/cards — mocking only the latter left the card
  // showing its first payload forever.
  await page.route('**/api/v1/briefing/refresh-cards**', route =>
    route.fulfill({ json: cards(!closed) })
  );
  await page.route(`**/api/v1/open-loops/${LOOP_ID}/close`, route => {
    closed = true;
    return route.fulfill({ json: { id: LOOP_ID } });
  });

  await page.goto('/fr/dashboard');
  // The per-item actions moved behind ONE trigger per row (2026-08-03): a row
  // of chips took a quarter to a third of the line and truncated the
  // commitment's own words. What the action DOES is unchanged.
  const trigger = page.getByRole('button', { name: 'Autres actions' }).first();
  await expect(trigger).toBeVisible({ timeout: 25_000 });
  await trigger.click();

  const done = page.getByRole('menuitem', { name: 'Marquer comme fait' });
  await expect(done).toBeVisible();
  await done.click();

  // The row must GO — that is what stops the second click from hitting a
  // commitment the API already closed.
  await expect(page.getByText('Rendre la perceuse')).toHaveCount(0, { timeout: 15_000 });
  expect(closes, 'exactly one close request').toHaveLength(1);
});
