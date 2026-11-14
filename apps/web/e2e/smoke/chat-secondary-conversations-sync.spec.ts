import { test, expect, waitForMockGate } from '../fixtures';
import { installApiCatchAll, registerRoutes, stopApiRequests } from '../fixtures/api-mock';
import { dashboardShellMocks } from '../fixtures/dashboard-shell';
import { ANNEX_DISCUSSION_ID, discussionFixture } from '../fixtures/discussions';

const STREAM = 'synthetic-annex-stream';
const ANSWER = 'Réponse reprise dans Voyage';
const transcript =
  `data: ${JSON.stringify({ type: 'token', content: ANSWER })}\n\n` +
  'data: {"type":"done","content":""}\n\n';

for (const backgroundRuns of [false, true]) {
  test(`switching during a turn respects background runs (${backgroundRuns})`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const user = await authenticate({ language: 'fr' });
    const fixture = discussionFixture(user.id, { annexTitle: 'Voyage', backgroundRuns });
    const finish = Promise.withResolvers<void>();
    let active = false;
    let sends = 0;
    const subscriptions: string[] = [];
    await mockApi([
      ...fixture.routes,
      {
        url: '**/api/v1/agents/chat/stream',
        method: 'POST',
        handler: async (route, signal) => {
          sends += 1;
          const request: unknown = route.request().postDataJSON();
          expect(request).toMatchObject({
            conversation_id: ANNEX_DISCUSSION_ID,
            conversation_revision: 0,
          });
          active = true;
          if (!(await waitForMockGate(finish.promise, signal))) return;
          active = false;
          await route.fulfill({ contentType: 'text/event-stream', body: transcript });
        },
      },
      {
        url: '**/api/v1/agents/runs/active?*',
        method: 'GET',
        handler: async route => {
          const query = new URL(route.request().url()).searchParams;
          await route.fulfill({
            json: active
              ? {
                  active,
                  stream_id: STREAM,
                  conversation_id: ANNEX_DISCUSSION_ID,
                  conversation_revision: 0,
                  conversation_kind: 'secondary',
                  title: 'Voyage',
                  selected: query.get('conversation_id') === ANNEX_DISCUSSION_ID,
                  can_resume: true,
                }
              : { active: false },
          });
        },
      },
      {
        url: `**/api/v1/agents/runs/${STREAM}/stream?*`,
        method: 'GET',
        handler: async route => {
          subscriptions.push(route.request().url());
          await route.fulfill({ contentType: 'text/event-stream', body: transcript });
        },
      },
    ]);
    await page.goto(`/fr/dashboard/chat?conversation=${ANNEX_DISCUSSION_ID}`);
    await expect(page.getByText('Historique annexe')).toBeVisible();
    const composer = page.locator('textarea').first();
    await composer.fill('Tour en cours');
    await composer.press('Enter');
    await expect.poll(() => sends).toBe(1);
    const annex = page.getByRole('button', { name: 'Discussions — Voyage', exact: true });
    const list = page.getByRole('dialog', { name: 'Discussions', exact: true });
    const mainRow = list.getByRole('button', { name: 'Principale', exact: true });
    await annex.click();
    if (!backgroundRuns) {
      await expect(mainRow).toBeDisabled();
      await expect(
        list.getByRole('status').filter({
          hasText: /^Attends la fin de la réponse ou arrête-la pour changer de discussion\.$/,
        })
      ).toBeVisible();
      finish.resolve();
      await expect(mainRow).toBeEnabled();
      await page.keyboard.press('Escape');
      await expect(page.getByText(ANSWER)).toBeVisible();
      expect(subscriptions).toEqual([]);
      return;
    }

    await mainRow.click();
    await expect(page.getByText('Historique principal')).toBeVisible();
    await expect(page.getByText(ANSWER)).toHaveCount(0);
    expect(subscriptions).toEqual([]);
    await page.getByRole('button', { name: 'Discussions — Principale', exact: true }).click();
    await list.getByRole('button', { name: 'Voyage', exact: true }).click();
    await expect(page.getByText(ANSWER)).toBeVisible();
    expect(subscriptions).toHaveLength(1);
    const target = new URL(subscriptions[0]).searchParams;
    expect(target.get('conversation_id')).toBe(ANNEX_DISCUSSION_ID);
    expect(target.get('conversation_revision')).toBe('0');
    expect(sends).toBe(1);
  });
}

test('deleting an annex withdraws it in another tab and preserves the Main draft', async ({
  page,
  context,
  authenticate,
  mockApi,
}) => {
  const user = await authenticate({ language: 'fr' });
  const fixture = discussionFixture(user.id, { annexTitle: 'Voyage' });
  await mockApi(fixture.routes);

  const annexTab = await context.newPage();
  const committed = Promise.withResolvers<void>();
  let announced = false;
  try {
    await installApiCatchAll(annexTab);
    await registerRoutes(annexTab, [
      ...dashboardShellMocks,
      { url: '**/api/v1/auth/me', json: user },
      ...fixture.routes,
      {
        url: '**/api/v1/notifications/stream',
        handler: async (route, signal) => {
          if (announced || !(await waitForMockGate(committed.promise, signal))) return;
          announced = true;
          const event = { type: 'conversation_reset', conversation_id: ANNEX_DISCUSSION_ID };
          await route.fulfill({
            contentType: 'text/event-stream',
            body: `event: notification\ndata: ${JSON.stringify(event)}\n\n`,
          });
        },
      },
    ]);
    await page.goto('/fr/dashboard/chat');
    await expect(page.getByText('Historique principal')).toBeVisible();
    const mainDraft = page.locator('textarea').first();
    await mainDraft.fill('Brouillon principal');

    await annexTab.goto(`/fr/dashboard/chat?conversation=${ANNEX_DISCUSSION_ID}`);
    await expect(annexTab.getByText('Historique annexe')).toBeVisible();
    await annexTab.locator('textarea').first().fill('Brouillon annexe');
    await annexTab.waitForFunction(
      text =>
        Object.values(localStorage).some(
          value => typeof value === 'string' && value.includes(text)
        ),
      'Brouillon annexe'
    );

    await page.bringToFront();
    await page.getByRole('button', { name: 'Discussions — Principale', exact: true }).click();
    await page.getByRole('button', { name: 'Supprimer Voyage', exact: true }).click();
    const confirmation = page.getByRole('alertdialog', { name: 'Supprimer « Voyage » ?' });
    await confirmation.getByRole('button', { name: 'Supprimer', exact: true }).click();
    await expect(confirmation).toBeHidden();
    expect(fixture.retirements).toHaveLength(1);

    await annexTab.bringToFront();
    committed.resolve();
    await expect(annexTab.getByText('Cette discussion n’est plus accessible.')).toBeVisible();
    await expect(annexTab.getByText('Historique annexe')).toHaveCount(0);
    const recovered = annexTab.getByRole('textbox', {
      name: 'Tu peux récupérer le texte de ton brouillon.',
    });
    await expect(recovered).toHaveValue('Brouillon annexe');
    await expect(recovered).not.toBeEditable();
    await annexTab.getByRole('button', { name: 'Ouvrir Principale', exact: true }).click();
    await expect(annexTab.locator('textarea').first()).toHaveValue('Brouillon principal');
    await expect(page.getByText('Historique principal')).toBeVisible();
    await expect(mainDraft).toHaveValue('Brouillon principal');
    expect(fixture.turns).toHaveLength(0);
  } finally {
    try {
      await stopApiRequests(annexTab);
    } finally {
      await annexTab.close();
    }
  }
});
