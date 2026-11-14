import { scanPage } from './scan';
import { test, expect } from '../fixtures';
import { ANNEX_DISCUSSION_ID, discussionFixture } from '../fixtures/discussions';

test('the discussion catalogue and title form are accessible at mobile width', async ({
  page,
  authenticate,
  mockApi,
}, info) => {
  await page.setViewportSize({ width: 320, height: 780 });
  const user = await authenticate({ language: 'fr', theme: 'oled' });
  await mockApi(discussionFixture(user.id, { annexTitle: 'Observatoire '.repeat(25) }).routes);
  await page.goto(`/fr/dashboard/chat?conversation=${ANNEX_DISCUSSION_ID}`);
  const trigger = page.getByRole('button', { name: /^Discussions — Observatoire/ });
  await trigger.press('Enter');
  const dialog = page.getByRole('dialog', { name: 'Discussions', exact: true });
  await expect(dialog).toBeVisible();
  const catalogue = await scanPage(page, info, 'discussion catalogue', '[role="dialog"]');
  expect(catalogue.blocking, catalogue.summary).toEqual([]);

  await dialog.getByRole('button', { name: 'Nouvelle discussion' }).press('Enter');
  const form = page.getByRole('dialog', { name: 'Nouvelle discussion', exact: true });
  const title = form.getByRole('textbox', { name: 'Titre' });
  await expect(title).toBeFocused();
  // An empty field is an answer — the first message names the discussion. A
  // title nobody can read is the error this form still shows.
  await title.fill('​');
  await form.getByRole('button', { name: 'Créer', exact: true }).press('Enter');
  await expect(title).toHaveAccessibleDescription('Ce titre n’est pas accepté.');
  const invalidTitle = await scanPage(page, info, 'refused discussion title', '[role="dialog"]');
  expect(invalidTitle.blocking, invalidTitle.summary).toEqual([]);
  await page.keyboard.press('Escape');
  await expect(form).toBeHidden();
  await page.keyboard.press('Escape');
  await expect(trigger).toBeFocused();
});
