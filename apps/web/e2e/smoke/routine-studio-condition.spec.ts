/**
 * Routine studio (N-07) — the condition + approval fields reach the dialog.
 *
 * Unit tests cover the payload assembly, the coherence rules, and the
 * condition-config toggling. What only a browser proves is the INTEGRATION:
 * the N-07 studio fields (trigger kind, propose-first switch) actually render
 * inside the create dialog a real user opens — the "invisible feature" class
 * this whole review is about. The Radix Select option-switching itself is
 * exercised by the component unit tests, not re-flaked here.
 */
import { test, expect, type MockRoute } from '../fixtures';

const ROUTES: MockRoute[] = [
  { url: '**/api/v1/scheduled-actions', method: 'GET', json: { scheduled_actions: [], total: 0 } },
  { url: '**/api/v1/usage/**', json: {} },
];

test.describe('routine studio (N-07)', () => {
  test('the create dialog exposes the trigger kind and propose-first fields', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    // Deep-link straight to the scheduled-actions section (Features tab).
    await page.goto('/fr/dashboard/settings?section=scheduled-actions');

    // Open the create dialog ("Ajouter").
    await page.getByRole('button', { name: 'Ajouter' }).first().click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible({ timeout: 30_000 });

    // N-07 fields present: the trigger-kind selector and the approval switch.
    await expect(dialog.getByText('Déclencheur')).toBeVisible();
    await expect(dialog.getByText(/Demander mon accord avant d'exécuter/)).toBeVisible();
    // The propose-first toggle is a real switch (keyboard-operable).
    await expect(dialog.getByRole('switch')).toBeVisible();
  });
});
