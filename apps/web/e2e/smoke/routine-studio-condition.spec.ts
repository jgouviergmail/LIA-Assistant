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
import AxeBuilder from '@axe-core/playwright';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import type { Route } from '@playwright/test';

import { test, expect, type MockRoute } from '../fixtures';

const french = JSON.parse(
  readFileSync(path.join(__dirname, '../../locales/fr/translation.json'), 'utf8')
) as {
  scheduled_actions: {
    studio: {
      requires_approval: string;
      requires_approval_hint: string;
      notify_only_when_new: string;
      notify_only_when_new_hint: string;
      notify_only_when_new_unavailable: string;
      condition: { page_change: string };
      query_label: { page_change: string };
      page_url: string;
      url_required: string;
    };
    templates: {
      label: string;
      hint: string;
      inbox_triage: { title: string; prompt: string; description: string };
    };
  };
};
const studio = french.scheduled_actions.studio;
const templates = french.scheduled_actions.templates;

const LISTING = {
  scheduled_actions: [],
  total: 0,
  condition_check_minutes: {
    calendar_event: 10,
    document_added: 10,
    mail_match: 10,
    // Deliberately not the weather's cadence: the page's own is stated (ADR-387).
    page_change: 45,
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
  // A time routine's caps, as the operator's settings publish them (ADR-268, 2026-10-30).
  recurrence_limits: { max_times_per_day: 12, min_step_minutes: 15, max_series_count: 500 },
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
    // The propose-first toggle is a real switch (keyboard-operable), and so is
    // « only when there is something new » beside it.
    await expect(dialog.getByRole('switch', { name: studio.requires_approval })).toBeVisible();
    await expect(dialog.getByRole('switch', { name: studio.notify_only_when_new })).toBeVisible();
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

  test('« only when there is something new » is sent with the routine, and asking first withdraws it', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const posted: Record<string, unknown>[] = [];
    await authenticate({ language: 'fr' });
    await mockApi([
      ...ROUTES,
      {
        url: '**/api/v1/scheduled-actions',
        method: 'POST',
        handler: async (route: Route) => {
          posted.push(route.request().postDataJSON() as Record<string, unknown>);
          await route.fulfill({
            status: 201,
            json: { ...CREATED, notify_only_when_new: true },
          });
        },
      },
    ]);
    await page.goto('/fr/dashboard/settings?section=scheduled-actions');
    await page.getByRole('button', { name: 'Ajouter' }).first().click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible({ timeout: 30_000 });

    await dialog.getByLabel('Titre', { exact: true }).fill('Veille facture');
    await dialog.getByLabel("Instruction pour l'assistant").fill('Préviens-moi');
    await dialog.getByRole('combobox', { name: 'Déclencheur' }).click();
    await page.getByRole('option', { name: 'Quand une condition est remplie' }).click();

    const approval = dialog.getByRole('switch', { name: studio.requires_approval });
    const quiet = dialog.getByRole('switch', { name: studio.notify_only_when_new });
    // A hint is a fact about its option: a screen reader hears it WITH the switch.
    await expect(quiet).toHaveAccessibleDescription(studio.notify_only_when_new_hint);
    await expect(approval).toHaveAccessibleDescription(studio.requires_approval_hint);
    // From the keyboard: a switch is operated with Space.
    await quiet.focus();
    await page.keyboard.press('Space');
    await expect(quiet).toBeChecked();

    // A routine that asks first always notifies: the option is switched off
    // and unavailable — said, never removed. A keyboard still reaches it, hears
    // why, and cannot set it.
    await approval.click();
    await expect(quiet).not.toBeChecked();
    await expect(quiet).toHaveAttribute('aria-disabled', 'true');
    await expect(quiet).toHaveAccessibleDescription(studio.notify_only_when_new_unavailable);
    await approval.focus();
    await page.keyboard.press('Tab');
    await expect(quiet).toBeFocused();
    await page.keyboard.press('Space');
    await expect(quiet).not.toBeChecked();
    await expect(quiet).toBeFocused();
    expect(
      (
        await new AxeBuilder({ page })
          .include('[role="dialog"]')
          .withTags(['wcag2a', 'wcag2aa'])
          .analyze()
      ).violations
    ).toEqual([]);

    await approval.click();
    await expect(quiet).not.toHaveAttribute('aria-disabled', 'true');
    await expect(quiet).toHaveAccessibleDescription(studio.notify_only_when_new_hint);
    await quiet.click();
    await dialog.getByRole('button', { name: 'Enregistrer' }).click();

    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0].notify_only_when_new).toBe(true);
    expect(posted[0].requires_approval).toBe(false);
  });

  test('a ready-made routine fills the form, and the request carries its words, clock and delivery', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const posted: Record<string, unknown>[] = [];
    await authenticate({ language: 'fr' });
    await mockApi([
      ...ROUTES,
      {
        url: '**/api/v1/scheduled-actions',
        method: 'POST',
        handler: async (route: Route) => {
          posted.push(route.request().postDataJSON() as Record<string, unknown>);
          await route.fulfill({
            status: 201,
            json: { ...CREATED, title: templates.inbox_triage.title, trigger_kind: 'time' },
          });
        },
      },
    ]);
    await page.goto('/fr/dashboard/settings?section=scheduled-actions');
    await page.getByRole('button', { name: 'Ajouter' }).first().click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible({ timeout: 30_000 });

    const list = dialog.getByRole('combobox', { name: templates.label, exact: true });
    await expect(list).toHaveAccessibleDescription(templates.hint);
    await list.focus();
    await list.selectOption({ label: templates.inbox_triage.title });

    // Its words, in the reader's language; what it does, said under the list,
    // which keeps the focus; and its delivery: quiet unless something is new.
    await expect(dialog.getByLabel('Titre', { exact: true })).toHaveValue(
      templates.inbox_triage.title
    );
    await expect(dialog.getByLabel("Instruction pour l'assistant")).toHaveValue(
      templates.inbox_triage.prompt
    );
    await expect(list).toHaveAccessibleDescription(templates.inbox_triage.description);
    await expect(list).toBeFocused();
    await expect(dialog.getByRole('switch', { name: studio.notify_only_when_new })).toBeChecked();
    expect(
      (
        await new AxeBuilder({ page })
          .include('[role="dialog"]')
          .withTags(['wcag2a', 'wcag2aa'])
          .analyze()
      ).violations
    ).toEqual([]);
    expect(posted).toHaveLength(0); // nothing is scheduled before the save

    await dialog.getByRole('button', { name: 'Enregistrer' }).click();

    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0]).toMatchObject({
      title: templates.inbox_triage.title,
      action_prompt: templates.inbox_triage.prompt,
      trigger_kind: 'time',
      requires_approval: false,
      notify_only_when_new: true,
      recurrence: {
        freq: 'weekly',
        byweekday: [1, 2, 3, 4, 5],
        times: { mode: 'at', at: [{ hour: 8, minute: 0 }] },
      },
    });
    expect(posted[0]).not.toHaveProperty('condition_config');
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

  test('a page is watched by its address, a line filter included (ADR-387)', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const watched = 'https://shop.example.org/chair';
    const posted: Record<string, unknown>[] = [];
    await authenticate({ language: 'fr' });
    await mockApi([
      ...ROUTES,
      {
        url: '**/api/v1/scheduled-actions',
        method: 'POST',
        handler: async (route: Route) => {
          posted.push(route.request().postDataJSON() as Record<string, unknown>);
          await route.fulfill({
            status: 201,
            json: {
              ...CREATED,
              title: 'Prix de la chaise',
              condition_config: { type: 'page_change', url: watched, contains: '€' },
              schedule_display: 'Vérifiée environ toutes les 45 min',
              check_interval_minutes: 45,
            },
          });
        },
      },
    ]);
    await page.goto('/fr/dashboard/settings?section=scheduled-actions');
    await page.getByRole('button', { name: 'Ajouter' }).first().click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible({ timeout: 30_000 });

    await dialog.getByLabel('Titre', { exact: true }).fill('Prix de la chaise');
    await dialog
      .getByLabel("Instruction pour l'assistant")
      .fill('Préviens-moi si le prix passe sous 300 €');
    await dialog.getByRole('combobox', { name: 'Déclencheur' }).click();
    await page.getByRole('option', { name: 'Quand une condition est remplie' }).click();
    await dialog.getByRole('combobox', { name: 'Condition' }).click();
    await page.getByRole('option', { name: studio.condition.page_change }).click();

    // The address is asked for before anything is saved.
    await expect(dialog.getByRole('alert')).toHaveText(studio.url_required);
    await expect(dialog.getByRole('button', { name: 'Enregistrer' })).toBeDisabled();
    await dialog.getByLabel(studio.page_url).fill(watched);
    await dialog.getByLabel(studio.query_label.page_change).fill('€');
    // The page's own clock, as the server publishes it.
    await expect(dialog.getByText(/Vérifiée environ toutes les 45 min/)).toBeVisible();
    const axe = await new AxeBuilder({ page }).include('[role="dialog"]').analyze();
    expect(axe.violations).toEqual([]);

    await dialog.getByRole('button', { name: 'Enregistrer' }).click();
    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0].trigger_kind).toBe('condition');
    expect(posted[0].condition_config).toEqual({
      type: 'page_change',
      url: watched,
      contains: '€',
    });
    expect(posted[0]).not.toHaveProperty('recurrence');
  });
});
