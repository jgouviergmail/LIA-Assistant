import { test, expect } from '../fixtures';
import {
  ANNEX_DISCUSSION_ID,
  UNTITLED_DISCUSSION,
  discussionFixture,
} from '../fixtures/discussions';
import { probeControls, waitForStableControls } from './control-probe';

test('creates, switches, resets and deletes the reviewed discussion', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const user = await authenticate({ language: 'fr' });
  const fixture = discussionFixture(user.id);
  await mockApi(fixture.routes);
  await page.goto('/fr/dashboard/chat');
  const composer = page.locator('textarea').first();
  await expect(composer).toBeEnabled();
  await expect(page.getByText('Historique principal')).toBeVisible();
  await expect(page.getByText('Conversation du 9 novembre')).toHaveCount(0);
  await composer.fill('Mon brouillon principal');

  const mainBadge = page.getByRole('button', { name: 'Discussions — Principale', exact: true });
  await mainBadge.focus();
  await page.keyboard.press('Enter');
  const list = page.getByRole('dialog', { name: 'Discussions', exact: true });
  await expect(list.getByRole('button', { name: 'Principale', exact: true })).toHaveAttribute(
    'aria-current',
    'true'
  );
  await expect(list.getByRole('button', { name: 'Supprimer Principale', exact: true })).toHaveCount(
    0
  );
  await list.getByRole('button', { name: 'Nouvelle discussion' }).click();
  const create = page.getByRole('dialog', { name: 'Nouvelle discussion' });
  // A title is optional, an unreadable one is still refused: nothing is created.
  await create.getByRole('textbox', { name: 'Titre' }).fill('​');
  await create.getByRole('button', { name: 'Créer', exact: true }).click();
  await expect(create.getByRole('textbox', { name: 'Titre' })).toHaveAccessibleDescription(
    'Ce titre n’est pas accepté.'
  );
  expect(fixture.creates).toHaveLength(0);
  await create.getByRole('textbox', { name: 'Titre' }).fill('Voyage');
  await page.keyboard.press('Enter');
  const annexBadge = page.getByRole('button', { name: 'Discussions — Voyage', exact: true });
  await expect(annexBadge).toBeVisible();
  await expect(annexBadge).toBeFocused();
  await expect(composer).toHaveValue('');
  await expect(page.getByText('Historique principal')).toHaveCount(0);
  await expect(page.getByText('Historique annexe')).toBeVisible();
  const context = page.getByTestId('context-usage-pill');
  await expect(context).toHaveText('12%');
  await context.press('Enter');
  await expect(page.getByTestId('context-usage-totals')).toContainText('40 TOTAL');
  await expect(page.getByTestId('context-usage-totals')).toContainText(/0[.,]17/);
  await composer.fill('Tour annexe');
  await composer.press('Enter');
  await expect(page.getByText('Réponse dans la bonne discussion')).toBeVisible();
  expect(fixture.turns).toMatchObject([
    { message: 'Tour annexe', conversation_id: ANNEX_DISCUSSION_ID, conversation_revision: 0 },
  ]);
  await expect(context).toHaveText('20%');
  await expect(page.getByTestId('context-usage-totals')).toContainText('65 TOTAL');
  await expect(page.getByTestId('context-usage-totals')).toContainText(/0[.,]28/);

  await composer.fill('Brouillon à effacer');
  await annexBadge.click();
  await list.getByRole('button', { name: 'Renommer Voyage', exact: true }).click();
  const rename = page.getByRole('dialog', { name: 'Renommer', exact: true });
  await expect(rename.getByRole('textbox', { name: 'Titre' })).toHaveValue('Voyage');
  await rename.getByRole('textbox', { name: 'Titre' }).fill('Itinéraire');
  await page.keyboard.press('Enter');
  await expect(rename).toBeHidden();
  await page.keyboard.press('Escape');
  await expect(
    page.getByRole('button', { name: 'Discussions — Itinéraire', exact: true })
  ).toBeVisible();
  await expect(composer).toHaveValue('Brouillon à effacer');
  await expect(page.getByText('Réponse dans la bonne discussion')).toBeVisible();
  expect(fixture.renames).toEqual([
    { title: 'Itinéraire', expected_title: 'Voyage', expected_revision: 0 },
  ]);

  await page.getByRole('button', { name: 'Réinitialiser', exact: true }).click();
  const reset = page.getByRole('alertdialog', { name: 'Réinitialiser « Itinéraire » ?' });
  expect(fixture.retirements).toHaveLength(0);
  await reset.getByRole('button', { name: 'Réinitialiser', exact: true }).click();
  await expect(reset).toBeHidden();
  await expect(composer).toHaveValue('');
  await expect(page.getByText('Historique annexe')).toHaveCount(0);

  await page.getByRole('button', { name: 'Discussions — Itinéraire', exact: true }).click();
  await list.getByRole('button', { name: 'Supprimer Itinéraire', exact: true }).click();
  await page
    .getByRole('alertdialog', { name: 'Supprimer « Itinéraire » ?' })
    .getByRole('button', { name: 'Supprimer', exact: true })
    .click();
  await expect(mainBadge).toBeVisible();
  await expect(composer).toHaveValue('Mon brouillon principal');
  await expect(page.getByText('Historique principal')).toBeVisible();
  await expect(context).toHaveText('68%');
  await context.press('Enter');
  await expect(page.getByTestId('context-usage-totals')).toContainText('100 TOTAL');
  expect(fixture.retirements.map(request => request.expected_revision)).toEqual([0, 1]);
  await expect(page.getByText('Le nettoyage demande une nouvelle tentative.')).toBeVisible();
  await page.getByRole('button', { name: 'Relancer le nettoyage' }).click();
  await expect(page.getByText('Le nettoyage demande une nouvelle tentative.')).toHaveCount(0);
  await mainBadge.click();
  await expect(list.getByRole('button', { name: 'Itinéraire', exact: true })).toHaveCount(0);
});

test('an empty title creates the discussion, and every discussion offers its export', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const user = await authenticate({ language: 'fr' });
  const fixture = discussionFixture(user.id);
  await mockApi(fixture.routes);
  await page.goto('/fr/dashboard/chat');
  await expect(page.getByText('Historique principal')).toBeVisible();
  await page.getByRole('button', { name: 'Discussions — Principale', exact: true }).click();
  const list = page.getByRole('dialog', { name: 'Discussions', exact: true });
  await list.getByRole('button', { name: 'Nouvelle discussion' }).click();
  // Nothing typed: no title is sent, and the server names the discussion
  // until its first message does.
  await page
    .getByRole('dialog', { name: 'Nouvelle discussion' })
    .getByRole('button', { name: 'Créer', exact: true })
    .click();
  const badge = page.getByRole('button', {
    name: `Discussions — ${UNTITLED_DISCUSSION}`,
    exact: true,
  });
  await expect(badge).toBeVisible();
  expect(fixture.creates).toHaveLength(1);
  expect(fixture.creates[0]).not.toHaveProperty('title');

  // A download is a real link the browser follows, named for its discussion:
  // an annex by its identity and generation, Main with no selection.
  await badge.click();
  await expect(
    list.getByRole('link', { name: `Exporter ${UNTITLED_DISCUSSION}`, exact: true })
  ).toHaveAttribute(
    'href',
    `/api/v1/conversations/me/export?conversation_id=${ANNEX_DISCUSSION_ID}&conversation_revision=0`
  );
  await expect(
    list.getByRole('link', { name: 'Exporter Principale', exact: true })
  ).toHaveAttribute('href', '/api/v1/conversations/me/export');
});

test('a stale link cannot execute its request in Main or in the newer revision', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const user = await authenticate({ language: 'fr' });
  const fixture = discussionFixture(user.id, { annexTitle: 'Voyage' });
  await mockApi(fixture.routes);
  await page.goto(
    `/fr/dashboard/chat?conversation=${ANNEX_DISCUSSION_ID}&conversation_revision=9&intent=Message%20p%C3%A9rim%C3%A9`
  );
  await expect(page.getByText('Cette discussion n’est plus accessible.')).toBeVisible();
  expect(fixture.turns).toHaveLength(0);
  await page.getByRole('button', { name: 'Ouvrir Principale', exact: true }).click();
  await expect(page.getByText('Historique principal')).toBeVisible();
  expect(fixture.turns).toHaveLength(0);
});

for (const language of ['fr', 'en', 'de', 'es', 'it', 'zh']) {
  test(`loaded discussion controls fit at narrow and wide widths (${language})`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const user = await authenticate({ language, font_size: 19, theme: 'oled' });
    await mockApi(
      discussionFixture(user.id, { annexTitle: 'Observatoire '.repeat(35), creationEnabled: false })
        .routes
    );
    await page.goto(`/${language}/dashboard/chat?conversation=${ANNEX_DISCUSSION_ID}`);
    await expect(page.getByText('Historique annexe')).toBeVisible();
    for (const width of [320, 390, 768, 1024, 1280]) {
      await page.setViewportSize({ width, height: 850 });
      await waitForStableControls(page, 'chat-header');
      const layout = await probeControls(page, 'chat-header');
      expect(layout.clipped, `${language} at ${width}px`).toEqual([]);
      expect(layout.overlaps, `${language} at ${width}px`).toEqual([]);
    }
  });
}
