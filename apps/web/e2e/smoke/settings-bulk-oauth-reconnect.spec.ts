/** One browser action starts one provider authorization for selected services. */
import { test, expect, type MockRoute } from '../fixtures';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const googleConnectors = [
  { id: 'mail', connector_type: 'google_gmail', status: 'error', oauth_grant_id: 'grant-a' },
  { id: 'calendar', connector_type: 'google_calendar', status: 'error', oauth_grant_id: 'grant-a' },
];

test('one click starts one Google OAuth request for a verified account', async ({
  page, authenticate, mockApi,
}) => {
  await authenticate({ language: 'fr' });
  const bodies: unknown[] = [];
  const routes: MockRoute[] = [
    { url: '**/api/v1/connectors', json: { connectors: googleConnectors } },
    {
      url: '**/api/v1/connectors/oauth-bulk/google/authorize',
      method: 'POST',
      handler: async route => {
        bodies.push(route.request().postDataJSON());
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ authorization_url: 'https://accounts.google.com/o/oauth2/v2/auth?state=e2e' }),
        });
      },
    },
  ];
  await mockApi(routes);
  await page.route('https://accounts.google.com/**', route => route.fulfill({
    contentType: 'text/html', body: '<!doctype html><title>Google consent fixture</title>',
  }));
  await page.goto('/fr/dashboard/settings?section=connectors');
  await page.getByRole('button', { name: /Reconnexion requise/ }).first().click();
  await page.getByRole('button', { name: 'Reconnecter mes services Google' }).click();
  await expect(page).toHaveURL(/accounts\.google\.com/);
  expect(bodies).toEqual([{ connector_types: ['google_gmail', 'google_calendar'] }]);
});

test('different Microsoft accounts require a choice and stay within a phone viewport', async ({
  page, authenticate, mockApi,
}) => {
  await authenticate({ language: 'fr' });
  const bodies: unknown[] = [];
  await mockApi([
    { url: '**/api/v1/connectors', json: { connectors: [
      { id: 'mail', connector_type: 'microsoft_outlook', status: 'error', oauth_grant_id: 'first', metadata: { oauth_account_email: 'first@example.com' } },
      { id: 'calendar', connector_type: 'microsoft_calendar', status: 'error', oauth_grant_id: 'second', metadata: { oauth_account_email: 'second@example.com' } },
    ] } },
    {
      url: '**/api/v1/connectors/oauth-bulk/microsoft/authorize',
      method: 'POST',
      handler: async route => {
        bodies.push(route.request().postDataJSON());
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ authorization_url: 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?state=e2e' }),
        });
      },
    },
  ]);
  await page.route('https://login.microsoftonline.com/**', route => route.fulfill({
    contentType: 'text/html', body: '<!doctype html><title>Microsoft consent fixture</title>',
  }));
  await page.setViewportSize({ width: 390, height: 800 });
  await page.goto('/fr/dashboard/settings?section=connectors');
  await awaitStyledPage(page, 'Microsoft reconnect at 390px');
  await page.getByRole('button', { name: /Reconnexion requise/ }).first().click();
  await page.getByRole('button', { name: 'Reconnecter mes services Microsoft' }).click();
  const dialog = page.getByRole('dialog', { name: 'Reconnecter les services Microsoft' });
  await expect(dialog).toBeVisible();
  await expectNoOverflow(page, 'Microsoft account selection at 390px');
  await dialog.getByRole('checkbox', { name: /Microsoft Outlook/ }).check();
  await expect(dialog.getByRole('checkbox', { name: /Microsoft Calendar/ })).toBeDisabled();
  await dialog.getByRole('button', { name: 'Continuer avec les services sélectionnés' }).click();
  await expect(page).toHaveURL(/login\.microsoftonline\.com/);
  expect(bodies).toEqual([{ connector_types: ['microsoft_outlook'] }]);
});

test('Tout connecter Google starts exactly one consent without a persisted queue', async ({
  page, authenticate, mockApi,
}) => {
  await authenticate({ language: 'fr' });
  const bodies: unknown[] = [];
  await mockApi([
    { url: '**/api/v1/connectors', json: { connectors: [] } },
    {
      url: '**/api/v1/connectors/oauth-bulk/google/connect-all/authorize',
      method: 'POST',
      handler: async route => {
        bodies.push(route.request().postDataJSON());
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ authorization_url: 'https://accounts.google.com/o/oauth2/v2/auth?state=connect-e2e' }),
        });
      },
    },
  ]);
  await page.route('https://accounts.google.com/**', route => route.fulfill({
    contentType: 'text/html', body: '<!doctype html><title>Google consent fixture</title>',
  }));
  await page.goto('/fr/dashboard/settings?section=connectors');
  await page.getByRole('button', { name: /Services Google/ }).click();
  await page.getByRole('button', { name: 'Tout connecter' }).first().click();
  await expect(page).toHaveURL(/accounts\.google\.com/);
  expect(bodies).toEqual([{}]);
  expect(await page.evaluate(() => localStorage.getItem('google_bulk_connect_queue'))).toBeNull();
});

test('Tout connecter Microsoft adds absent services to the selected account on mobile', async ({
  page, authenticate, mockApi,
}) => {
  await authenticate({ language: 'fr' });
  const bodies: unknown[] = [];
  await mockApi([
    { url: '**/api/v1/connectors', json: { connectors: [
      { id: 'mail', connector_type: 'microsoft_outlook', status: 'active', oauth_grant_id: 'existing-grant', metadata: { oauth_account_email: 'same@example.com' } },
    ] } },
    {
      url: '**/api/v1/connectors/oauth-bulk/microsoft/connect-all/authorize',
      method: 'POST',
      handler: async route => {
        bodies.push(route.request().postDataJSON());
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ authorization_url: 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?state=connect-e2e' }),
        });
      },
    },
  ]);
  await page.route('https://login.microsoftonline.com/**', route => route.fulfill({
    contentType: 'text/html', body: '<!doctype html><title>Microsoft consent fixture</title>',
  }));
  await page.setViewportSize({ width: 390, height: 800 });
  await page.goto('/fr/dashboard/settings?section=connectors');
  await awaitStyledPage(page, 'Microsoft connect all at 390px');
  await page.getByRole('button', { name: /Services Microsoft/ }).last().click();
  await page.getByRole('button', { name: 'Tout connecter' }).click();
  const dialog = page.getByRole('dialog', { name: 'Choisir un compte Microsoft' });
  await expect(dialog).toBeVisible();
  await expectNoOverflow(page, 'Microsoft connect account selection at 390px');
  await dialog.getByRole('radio', { name: 'same@example.com' }).check();
  await dialog.getByRole('button', { name: 'Continuer avec ce compte' }).click();
  await expect(page).toHaveURL(/login\.microsoftonline\.com/);
  expect(bodies).toEqual([{ grant_id: 'existing-grant' }]);
});

test('Tout connecter is disabled when every absent Google service is blocked', async ({
  page, authenticate, mockApi,
}) => {
  await authenticate({ language: 'fr' });
  await mockApi([
    { url: '**/api/v1/connectors', json: { connectors: [
      { id: 'outlook', connector_type: 'microsoft_outlook', status: 'active' },
      ...['google_calendar', 'google_contacts', 'google_drive', 'google_tasks'].map((type, index) => ({
        id: `google-${index}`, connector_type: type, status: 'active',
      })),
    ] } },
  ]);
  await page.goto('/fr/dashboard/settings?section=connectors');
  await page.getByRole('button', { name: /Services Google/ }).last().click();
  await expect(page.getByRole('button', { name: 'Tout connecter' })).toBeDisabled();
});
