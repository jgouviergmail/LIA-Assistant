import { test, expect, loadedChatRoutes } from '../fixtures';
import { avatarConfig } from '../fixtures/simli';
import { appConfig } from '../fixtures/dashboard-shell';
import { awaitStyledPage } from './overflow-report';

test('avatar autosave recovers from refusal and completes during settings navigation', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate({ voice_enabled: false });
  const originalFace = '00000000-0000-4000-8000-000000000001';
  const chosenFace = '00000000-0000-4000-8000-000000000002';
  let confirmedFace = originalFace;
  const writes: unknown[] = [];
  let completeSave = () => {};
  const completion = new Promise<void>(resolve => {
    completeSave = resolve;
  });
  const configuration = () => ({ ...avatarConfig, enabled: false, face_id: confirmedFace });

  await mockApi([
    ...loadedChatRoutes(),
    {
      url: '**/api/v1/config',
      json: { ...appConfig, features: { ...appConfig.features, avatar_enabled: true } },
    },
    { url: /\/api\/v1\/connectors(?:\?fresh=true)?$/, json: { connectors: [] } },
    {
      url: '**/api/v1/avatars/config',
      handler: route => route.fulfill({ json: configuration() }),
    },
    {
      url: '**/api/v1/avatars/faces',
      json: [
        { id: originalFace, name: 'Original face', source: 'private' },
        { id: chosenFace, name: 'Chosen face', source: 'private' },
      ],
    },
    {
      url: '**/api/v1/avatars/settings',
      method: 'PUT',
      handler: async route => {
        writes.push(route.request().postDataJSON());
        if (writes.length === 1) {
          await route.fulfill({ status: 422, json: { detail: 'Choice refused by fixture' } });
          return;
        }
        await completion;
        confirmedFace = chosenFace;
        await route.fulfill({ json: configuration() });
      },
    },
  ]);

  try {
    await page.goto('/en/dashboard/settings?section=avatar');
    await awaitStyledPage(page, 'avatar autosave recovery');
    const picker = page.getByRole('combobox', { name: 'Avatar', exact: true });
    await expect(picker).toHaveText('Original face');
    await picker.click();
    await page.getByRole('option', { name: 'Chosen face', exact: true }).click();

    const section = page.locator('#settings-section-avatar');
    await expect(section.getByRole('alert')).toBeVisible();
    await expect(picker).toHaveText('Original face');
    await expect.poll(() => writes.length).toBe(1);

    const retry = section.getByRole('button', { name: 'Retry', exact: true });
    await retry.click();
    await expect.poll(() => writes.length).toBe(2);
    await expect(section.getByRole('status')).toHaveText('Saving…');
    await expect(retry).toBeFocused();
    await expect(retry).toHaveAttribute('aria-busy', 'true');
    // Force a second browser click through the aria-disabled actionability
    // check: the component's own guard must still prevent another write.
    await retry.click({ force: true });
    expect(writes).toHaveLength(2);

    // A real rail action changes the pane without reloading the dashboard.
    await page.getByRole('button', { name: 'Font size', exact: true }).click();
    await expect(page.locator('#settings-section-font-size')).toBeVisible();
    completeSave();
    await expect.poll(() => confirmedFace).toBe(chosenFace);

    await page.getByRole('button', { name: 'Speaking avatar', exact: true }).click();
    await expect(picker).toHaveText('Chosen face');
    await expect(section.getByRole('status')).toHaveText('Saved');
    await expect(section.getByRole('alert')).toHaveCount(0);
    expect(writes).toEqual([
      { enabled: false, face_id: chosenFace },
      { enabled: false, face_id: chosenFace },
    ]);
    await expect(page.getByRole('button', { name: 'Save', exact: true })).toHaveCount(0);
  } finally {
    completeSave();
  }
});
