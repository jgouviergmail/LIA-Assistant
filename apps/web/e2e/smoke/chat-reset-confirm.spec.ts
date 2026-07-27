/**
 * Resetting the conversation asks first, in-app (W4a).
 *
 * The most destructive action of the product went through `window.confirm`:
 * an OS dialog with no theme, no chosen typography, buttons labelled by the
 * operating system rather than by the app, and a blocked main thread. Its
 * wording was also wrong — it announced "the conversation history" while the
 * endpoint additionally purges every attachment of the user, AI-generated
 * images included.
 *
 * A browser is the only place that can prove the replacement really gates the
 * request: a unit test can assert the dialog renders, not that no DELETE goes
 * out while it is merely open.
 */
import { test, expect, type MockRoute } from '../fixtures';

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

test.describe('reset conversation confirmation', () => {
  test('opening the dialog sends nothing; confirming does', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });

    let resetCalls = 0;
    await mockApi([
      ...BASE,
      {
        url: '**/api/v1/conversations/me/reset',
        method: 'POST',
        handler: async route => {
          resetCalls += 1;
          await route.fulfill({
            status: 200,
            json: { status: 'success', message: 'ok', previous_message_count: 0 },
          });
        },
      },
    ]);

    await page.goto('/fr/dashboard/chat');
    await page.locator('textarea').first().waitFor({ state: 'visible' });

    await page.getByRole('button', { name: 'Supprimer' }).click();

    // The dialog is in-app (an OS confirm would never appear in the DOM) and
    // announces itself as an alert dialog — an irreversible choice must
    // interrupt assistive technology, not be read passively.
    const dialog = page.getByRole('alertdialog');
    await expect(dialog).toBeVisible();
    expect(resetCalls, 'nothing may be deleted while the dialog is merely open').toBe(0);

    // It says what is actually purged — attachments included.
    await expect(dialog.getByText(/pièces jointes/i)).toBeVisible();

    await dialog.getByRole('button', { name: 'Tout supprimer' }).click();
    await expect.poll(() => resetCalls).toBe(1);
  });

  test('cancelling deletes nothing and returns to the conversation', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });

    let resetCalls = 0;
    await mockApi([
      ...BASE,
      {
        url: '**/api/v1/conversations/me/reset',
        method: 'POST',
        handler: async route => {
          resetCalls += 1;
          await route.fulfill({ status: 200, json: {} });
        },
      },
    ]);

    await page.goto('/fr/dashboard/chat');
    await page.locator('textarea').first().waitFor({ state: 'visible' });

    await page.getByRole('button', { name: 'Supprimer' }).click();
    const dialog = page.getByRole('alertdialog');
    await dialog.getByRole('button', { name: 'Annuler' }).click();

    await expect(dialog).toBeHidden();
    expect(resetCalls).toBe(0);
    // The composer is usable again — the dialog did not leave the page locked.
    await expect(page.locator('textarea').first()).toBeEnabled();
  });

  test('the dialog is reachable and dismissible from the keyboard', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(BASE);

    await page.goto('/fr/dashboard/chat');
    await page.locator('textarea').first().waitFor({ state: 'visible' });
    await page.getByRole('button', { name: 'Supprimer' }).click();

    const dialog = page.getByRole('alertdialog');
    await expect(dialog).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
  });
});
