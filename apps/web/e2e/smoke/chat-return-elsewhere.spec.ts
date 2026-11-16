/**
 * A return named where it landed (ADR-378 amendment 2026-11-14).
 *
 * A call placed from an annex comes back to that annex. Seen from Main, its
 * toast says where it is and opens it, from the keyboard as from the pointer;
 * while leaving would cancel the turn on screen, it names the place without
 * offering to leave. The live event is the one the dispatcher publishes
 * (`proactive_phone_call`): the boundary used to refuse it, and no toast showed.
 */

import { test, expect, waitForMockGate } from '../fixtures';
import { ANNEX_DISCUSSION_ID, discussionFixture } from '../fixtures/discussions';

const RETURN = 'J’ai appelé le garage : la voiture sera prête demain.';

function callReturned(): string {
  const event = {
    type: 'proactive_phone_call',
    content: RETURN,
    title: 'Appel',
    target_id: 'call-1',
    metadata: { type: 'proactive_phone_call', conversation_id: ANNEX_DISCUSSION_ID },
  };
  return `event: notification\ndata: ${JSON.stringify(event)}\n\n`;
}

test('a return to an annex is named in its toast, which opens it from the keyboard', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const user = await authenticate({ language: 'fr' });
  const fixture = discussionFixture(user.id, { annexTitle: 'Voyage' });
  const ready = Promise.withResolvers<void>();
  let announced = false;
  await mockApi([
    ...fixture.routes,
    {
      url: '**/api/v1/notifications/stream',
      handler: async (route, signal) => {
        if (announced || !(await waitForMockGate(ready.promise, signal))) return;
        announced = true;
        await route.fulfill({ contentType: 'text/event-stream', body: callReturned() });
      },
    },
  ]);

  await page.goto('/fr/dashboard/chat');
  await expect(page.getByText('Historique principal')).toBeVisible();
  ready.resolve();

  const toast = page.locator('[data-sonner-toast]').filter({ hasText: RETURN });
  await expect(toast).toContainText(`Dans « Voyage » · ${RETURN}`);
  const open = toast.getByRole('button', { name: 'Ouvrir', exact: true });
  await open.focus();
  await page.keyboard.press('Enter');

  await expect(page.getByText('Historique annexe')).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`conversation=${ANNEX_DISCUSSION_ID}`));
  await expect(
    page.getByRole('button', { name: 'Discussions — Voyage', exact: true })
  ).toBeVisible();
});

const NOTICE = 'Pense à rappeler le dentiste avant midi.';

function mainNoticed(): string {
  // A notification for Main names no discussion: the server names annexes alone.
  const event = {
    type: 'proactive_heartbeat',
    content: NOTICE,
    title: 'LIA',
    target_id: 'hb-1',
    metadata: { type: 'proactive_heartbeat' },
  };
  return `event: notification\ndata: ${JSON.stringify(event)}\n\n`;
}

test('a notification for Main seen from an annex is named Main, and opens it', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const user = await authenticate({ language: 'fr' });
  const fixture = discussionFixture(user.id, { annexTitle: 'Voyage' });
  const ready = Promise.withResolvers<void>();
  let announced = false;
  await mockApi([
    ...fixture.routes,
    {
      url: '**/api/v1/notifications/stream',
      handler: async (route, signal) => {
        if (announced || !(await waitForMockGate(ready.promise, signal))) return;
        announced = true;
        await route.fulfill({ contentType: 'text/event-stream', body: mainNoticed() });
      },
    },
  ]);

  await page.goto(`/fr/dashboard/chat?conversation=${ANNEX_DISCUSSION_ID}`);
  await expect(page.getByText('Historique annexe')).toBeVisible();
  ready.resolve();

  const toast = page.locator('[data-sonner-toast]').filter({ hasText: NOTICE });
  await expect(toast).toContainText(`Dans « Principale » · ${NOTICE}`);
  const open = toast.getByRole('button', { name: 'Ouvrir', exact: true });
  await open.focus();
  await page.keyboard.press('Enter');

  await expect(page.getByText('Historique principal')).toBeVisible();
  await expect(page).not.toHaveURL(/conversation=/);
});

test('while leaving would cancel the turn, the toast names the annex and offers no way out', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const user = await authenticate({ language: 'fr' });
  const fixture = discussionFixture(user.id, { annexTitle: 'Voyage', backgroundRuns: false });
  const ready = Promise.withResolvers<void>();
  const finish = Promise.withResolvers<void>();
  let announced = false;
  await mockApi([
    ...fixture.routes,
    {
      url: '**/api/v1/agents/chat/stream',
      method: 'POST',
      handler: async (route, signal) => {
        if (!(await waitForMockGate(finish.promise, signal))) return;
        await route.fulfill({
          contentType: 'text/event-stream',
          body: 'data: {"type":"token","content":"Fini"}\n\ndata: {"type":"done","content":""}\n\n',
        });
      },
    },
    {
      url: '**/api/v1/notifications/stream',
      handler: async (route, signal) => {
        if (announced || !(await waitForMockGate(ready.promise, signal))) return;
        announced = true;
        await route.fulfill({ contentType: 'text/event-stream', body: callReturned() });
      },
    },
  ]);

  await page.goto('/fr/dashboard/chat');
  await expect(page.getByText('Historique principal')).toBeVisible();
  const composer = page.locator('textarea').first();
  await composer.fill('Un tour en cours');
  await composer.press('Enter');
  ready.resolve();

  const toast = page.locator('[data-sonner-toast]').filter({ hasText: RETURN });
  await expect(toast).toContainText(`Dans « Voyage » · ${RETURN}`);
  await expect(toast.getByRole('button', { name: 'Ouvrir', exact: true })).toHaveCount(0);
  finish.resolve();
  await expect(page.getByText('Historique principal')).toBeVisible();
});
