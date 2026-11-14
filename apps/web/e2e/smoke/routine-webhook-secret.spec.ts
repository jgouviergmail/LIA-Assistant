/**
 * A routine started by calls (ADR-386) — its address and its secret, read whole.
 *
 * The dialog that shows the secret once pushed past a phone's screen: its grid
 * track took the width of the signed-call example's longest line, and the
 * address and the secret sat in read-only fields whose end a narrow screen hid.
 * What only a browser proves is the GEOMETRY: at a phone's width and at a
 * desktop's, the dialog stays inside the viewport, nothing in it overflows
 * sideways, and the address and the secret are shown whole. The page is
 * screened by axe too, and nothing that carries the secret is offered to the
 * selection assist.
 */
import AxeBuilder from '@axe-core/playwright';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import type { Route } from '@playwright/test';

import { test, expect, type MockRoute } from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';

const french = JSON.parse(
  readFileSync(path.join(__dirname, '../../locales/fr/translation.json'), 'utf8')
) as {
  scheduled_actions: {
    studio: { trigger_kind: string; kind_webhook: string };
    webhook: { secret_title: string; address: string; secret: string; example: string };
  };
};
const studio = french.scheduled_actions.studio;
const webhook = french.scheduled_actions.webhook;

const ADDRESS = 'https://lia.example.org/api/v1/hooks/routines/pA9xK2mQ7vR4tY1wZ8bN3cL6eT0uW5sDq';
const SECRET = 'xQ3m-Zr8_vK2pL9tY6wB1nH4cF7dJ0sA5eG2uR8iO3kLmVb'; // gitleaks:allow

const LISTING = {
  scheduled_actions: [],
  total: 0,
  condition_check_minutes: { task_overdue: 10 },
  condition_max_fires_per_day: 12,
  weather_condition_rule: { horizon_hours: 3, min_precipitation_percent: 65 },
  recurrence_limits: { max_times_per_day: 12, min_step_minutes: 15, max_series_count: 500 },
};

/** The routine as the API answers its creation: its address, and the secret once. */
const CREATED = {
  id: '00000000-0000-4000-8000-00000000a386',
  user_id: '00000000-0000-4000-8000-000000000001',
  title: 'Sonnette',
  action_prompt: 'Dis-moi qui a sonné',
  recurrence: null,
  user_timezone: 'Europe/Paris',
  trigger_kind: 'webhook',
  condition_config: null,
  requires_approval: false,
  notify_only_when_new: false,
  execution_mode: 'react',
  next_trigger_at: null,
  is_enabled: true,
  status: 'active',
  last_executed_at: null,
  execution_count: 0,
  consecutive_failures: 0,
  last_error: null,
  schedule_display: "Quand un autre système l'appelle",
  times_of_day: [],
  runs_per_day: 0,
  next_occurrences: [],
  week_slots: [],
  check_interval_minutes: null,
  last_checked_at: null,
  last_check_error: null,
  mcp_preapproved_servers: [],
  webhook_url: ADDRESS,
  new_webhook_secret: SECRET,
  created_at: '2026-11-13T21:00:00Z',
  updated_at: '2026-11-13T21:00:00Z',
};

const ROUTES: MockRoute[] = [
  // The deployment mounts the third clock (the operator's switch is open by default).
  {
    url: '**/api/v1/config',
    json: { ...appConfig, features: { ...appConfig.features, routine_webhooks_enabled: true } },
  },
  { url: '**/api/v1/scheduled-actions', method: 'GET', json: LISTING },
  {
    url: '**/api/v1/scheduled-actions/week',
    method: 'GET',
    json: { actions: [], generated_at: '2026-11-13T21:00:00Z' },
  },
  { url: '**/api/v1/usage/**', json: {} },
  {
    url: '**/api/v1/scheduled-actions',
    method: 'POST',
    handler: async (route: Route) => {
      await route.fulfill({ status: 201, json: CREATED });
    },
  },
];

const VIEWPORTS = [
  { name: 'phone', width: 375, height: 740 },
  { name: 'desktop', width: 1280, height: 800 },
] as const;

for (const viewport of VIEWPORTS) {
  test(`the secret drawn at creation is read whole on a ${viewport.name}`, async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/settings?section=scheduled-actions');
    await page.getByRole('button', { name: 'Ajouter' }).first().click();
    const form = page.getByRole('dialog');
    await expect(form).toBeVisible({ timeout: 30_000 });
    await form.getByLabel('Titre', { exact: true }).fill('Sonnette');
    await form.getByLabel("Instruction pour l'assistant").fill('Dis-moi qui a sonné');
    await form.getByRole('combobox', { name: studio.trigger_kind }).click();
    await page.getByRole('option', { name: studio.kind_webhook }).click();
    await form.getByRole('button', { name: 'Enregistrer' }).click();

    const shown = page.getByRole('dialog', { name: webhook.secret_title });
    await expect(shown).toBeVisible();
    await expect(shown.getByRole('group', { name: webhook.secret })).toContainText(SECRET);

    // Inside the screen, and nothing in it pushed sideways.
    const box = await shown.boundingBox();
    expect(box).not.toBeNull();
    const dialogBox = box!;
    expect(dialogBox.x).toBeGreaterThanOrEqual(0);
    expect(dialogBox.x + dialogBox.width).toBeLessThanOrEqual(viewport.width);
    expect(
      await shown.evaluate(element => element.scrollWidth - element.clientWidth)
    ).toBeLessThanOrEqual(1);
    const example = shown.getByRole('figure', { name: webhook.example });
    expect(
      await example.locator('pre').evaluate(element => element.scrollWidth - element.clientWidth)
    ).toBeLessThanOrEqual(1);

    // The address and the secret are shown WHOLE, inside the dialog.
    for (const value of [ADDRESS, SECRET]) {
      const text = shown.getByText(value, { exact: true });
      await expect(text).toBeVisible();
      const valueBox = (await text.boundingBox())!;
      expect(valueBox.x).toBeGreaterThanOrEqual(dialogBox.x);
      expect(valueBox.x + valueBox.width).toBeLessThanOrEqual(dialogBox.x + dialogBox.width);
      expect(
        await text.evaluate(element => element.scrollWidth - element.clientWidth)
      ).toBeLessThanOrEqual(1);
      expect(
        await text.evaluate(element => element.closest('[data-selection-assist="off"]') !== null)
      ).toBe(true);
    }

    // The paint itself, kept beside the run for a reviewer's eye.
    const shot = testInfo.outputPath(`secret-dialog-${viewport.name}.png`);
    await page.screenshot({ path: shot, fullPage: false });
    await testInfo.attach(`secret-dialog-${viewport.name}`, {
      path: shot,
      contentType: 'image/png',
    });

    const axe = await new AxeBuilder({ page }).include('[role="dialog"]').analyze();
    expect(axe.violations).toEqual([]);
  });
}
