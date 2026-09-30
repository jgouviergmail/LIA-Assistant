/**
 * Routine studio (N-07, ADR-322) — one clock per routine, chosen first.
 *
 * Unit tests cover the payload assembly, the coherence rules and the
 * condition-config toggling. What only a browser proves is the INTEGRATION:
 * the fields actually render inside the dialog a real user opens (the
 * "invisible feature" class), and — since ADR-322 — that choosing a condition
 * REMOVES the schedule from the form and from the request, the system's check
 * cadence being stated instead, as the server publishes it.
 */
import type { Route } from '@playwright/test';

import { test, expect, type MockRoute } from '../fixtures';

const LISTING = {
  scheduled_actions: [],
  total: 0,
  condition_check_minutes: {
    calendar_event: 10,
    document_added: 10,
    mail_match: 10,
    task_overdue: 10,
    weather_change: 60,
  },
  condition_max_fires_per_day: 12,
  // Deliberately NOT the defaults: the sentence must read what is published.
  weather_condition_rule: {
    horizon_hours: 3,
    min_precipitation_percent: 65,
    source: 'google_weather',
  },
};

/** What the API answers to the create: the routine as it now stands. */
const CREATED = {
  id: '00000000-0000-4000-8000-00000000c322',
  user_id: '00000000-0000-4000-8000-000000000001',
  title: 'Veille facture',
  action_prompt: 'Préviens-moi',
  recurrence: null,
  user_timezone: 'Europe/Paris',
  trigger_kind: 'condition',
  condition_config: { type: 'task_overdue', until: '2099-12-31' },
  requires_approval: false,
  execution_mode: 'react',
  next_trigger_at: '2026-09-25T10:07:00Z',
  is_enabled: true,
  status: 'active',
  last_executed_at: null,
  execution_count: 0,
  consecutive_failures: 0,
  last_error: null,
  schedule_display: "Vérifiée environ toutes les 10 min, jusqu'au 31/12/2099",
  times_of_day: [],
  runs_per_day: 0,
  next_occurrences: [],
  week_slots: [],
  check_interval_minutes: 10,
  last_checked_at: null,
  last_check_error: null,
  created_at: '2026-09-25T10:00:00Z',
  updated_at: '2026-09-25T10:00:00Z',
};

const ROUTES: MockRoute[] = [
  { url: '**/api/v1/scheduled-actions', method: 'GET', json: LISTING },
  {
    url: '**/api/v1/scheduled-actions/week',
    method: 'GET',
    json: { actions: [], generated_at: '2026-09-25T10:00:00Z' },
  },
  { url: '**/api/v1/usage/**', json: {} },
];

test.describe('routine studio (N-07, ADR-322)', () => {
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

  test('a condition routine is created with no schedule, until its last day', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const posted: unknown[] = [];
    await authenticate({ language: 'fr' });
    await mockApi([
      ...ROUTES,
      {
        url: '**/api/v1/scheduled-actions',
        method: 'POST',
        handler: async (route: Route) => {
          posted.push(route.request().postDataJSON());
          await route.fulfill({ status: 201, json: CREATED });
        },
      },
    ]);
    await page.goto('/fr/dashboard/settings?section=scheduled-actions');
    await page.getByRole('button', { name: 'Ajouter' }).first().click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible({ timeout: 30_000 });

    await dialog.getByLabel('Titre', { exact: true }).fill('Veille facture');
    await dialog.getByLabel("Instruction pour l'assistant").fill('Préviens-moi');
    // The schedule is there until a condition is chosen…
    await expect(dialog.getByRole('group', { name: 'Quand', exact: true })).toBeVisible();
    await dialog.getByRole('combobox', { name: 'Déclencheur' }).click();
    await page.getByRole('option', { name: 'Quand une condition est remplie' }).click();

    // …then it is gone, and the system's clock is stated instead.
    await expect(dialog.getByRole('group', { name: 'Quand', exact: true })).toHaveCount(0);
    await expect(
      dialog.getByText(/Vérifiée environ toutes les 10 min, jour et nuit/)
    ).toBeVisible();
    await dialog.getByLabel("Surveiller jusqu'au (facultatif)").fill('2099-12-31');
    await dialog.getByRole('button', { name: 'Enregistrer' }).click();

    await expect.poll(() => posted.length).toBe(1);
    const body = posted[0] as Record<string, unknown>;
    expect(body.trigger_kind).toBe('condition');
    expect(body.condition_config).toEqual({ type: 'task_overdue', until: '2099-12-31' });
    expect(body).not.toHaveProperty('recurrence');
    // The new routine's card states the system's clock, and no next run.
    await expect(
      page.locator('[data-routine-card]').filter({ hasText: 'Veille facture' })
    ).toContainText('Pas encore vérifiée');
  });

  test('a weather routine states when it fires, as the server publishes it', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/settings?section=scheduled-actions');
    await page.getByRole('button', { name: 'Ajouter' }).first().click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible({ timeout: 30_000 });

    await dialog.getByRole('combobox', { name: 'Déclencheur' }).click();
    await page.getByRole('option', { name: 'Quand une condition est remplie' }).click();
    await dialog.getByRole('combobox', { name: 'Condition' }).click();
    await page.getByRole('option', { name: 'Changement de météo' }).click();

    // Every kind, the published horizon and STRICT floor, the one source.
    await expect(
      dialog.getByText(
        'Se déclenche quand Google Weather prévoit de la pluie, de la bruine, de la neige ' +
          "ou un orage dans les 3 prochaines heures (l'heure en cours comprise), avec une " +
          'probabilité de précipitations supérieure à 65 %.'
      )
    ).toBeVisible();
    await expect(dialog.getByText(/Vérifiée environ toutes les 60 min/)).toBeVisible();
  });
});
