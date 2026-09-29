/** Native routing controls: confirmed state, keyboard focus and narrow-screen layout. */
import { test, expect } from '../fixtures';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';
import { scanPage } from '../a11y/scan';

for (const width of [1280, 320]) {
  test(`Jev routing preserves focus and preferences at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    const pageErrors: string[] = [];
    const consoleErrors: string[] = [];
    const unmatchedRequests: string[] = [];
    page.on('response', response => {
      if (response.status() === 501) unmatchedRequests.push(new URL(response.url()).pathname);
    });
    page.on('pageerror', error => pageErrors.push(error.message));
    page.on('console', message => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    await page.setViewportSize({ width, height: 900 });
    await authenticate({ language: 'fr', is_superuser: true });
    let enabled = false;
    const locals: Record<string, boolean> = Object.fromEntries(
      [
        'meeting_template',
        'filter_email',
        'filter_event',
        'filter_task',
        'filter_file',
        'radio_verification',
        'consultation_path',
        'initiative_utility',
        'consultation_bounded',
        'observe_memory',
        'observe_interests',
        'observe_journal',
        'observe_open_loops',
        'hitl_exclusion',
        'filter_reminder',
        'filter_ticket',
        'filter_mcp',
        'filter_document',

      ].map(usage => [usage, usage === 'meeting_template'])
    );
    const writes: unknown[] = [];
    await mockApi([
      { url: '**/api/v1/connectors', json: { connectors: [] } },
      { url: '**/api/v1/habits/presence', json: {} },
      { url: '**/api/v1/agents/runs/active', json: null },
      { url: '**/api/v1/notifications/broadcasts/unread', json: { broadcasts: [] } },
      { url: '**/api/v1/notifications/stream', handler: route => route.fulfill({ status: 204 }) },
      {
        url: '**/api/v1/journals/portrait',
        json: { full: null, brief: null, compiled_at: null, sources: null },
      },
      {
        url: '**/api/v1/system-settings/debug-panel-status',
        json: { enabled: false, user_access_available: false },
      },
      {
        url: '**/api/v1/admin/llm-config/jev',
        handler: async route => {
          if (route.request().method() === 'PATCH') {
            const body = route.request().postDataJSON() as {
              usage: string | null;
              enabled: boolean;
            };
            writes.push(body);
            if (body.usage === null) enabled = body.enabled;
            else locals[body.usage] = body.enabled;
          }
          await route.fulfill({
            json: {
              enabled,
              usages: Object.entries(locals).map(([usage, local]) => ({
                usage,
                label_key: `settings.admin.jev.usages.${usage}`,
                llm_type:
                  usage === 'meeting_template' ? 'meeting_template_selection' : `jev_${usage}`,
                enabled: local,
                effective: enabled && local,
                readiness: 'ready',
              })),
            },
          });
        },
      },
    ]);
    await page.goto('/fr/dashboard/settings?section=admin-jev');
    const section = page.locator('#settings-section-admin-jev');
    await expect(section).toBeVisible({ timeout: 60_000 });
    await awaitStyledPage(page, 'jev');
    const global = section.getByRole('switch', { name: 'Activer JEV', exact: true });
    const usage = section.getByRole('switch', {
      name: 'Choix automatique du modèle de compte rendu',
    });
    await expect(global).not.toBeChecked();
    await expect(usage).toBeChecked();
    await expect(section.getByRole('switch')).toHaveCount(19);
    const initiative = section.getByRole('switch', { name: 'Utilité de l’initiative' });
    await initiative.click();
    await expect(initiative).toBeChecked();
    await expect(usage).toBeChecked();
    await global.focus();
    await page.keyboard.press('Space');
    await expect(global).toBeChecked();
    await expect(global).toBeFocused();
    await page.keyboard.press('Space');
    await expect(global).not.toBeChecked();
    await expect(usage).toBeChecked();
    expect(writes).toEqual([
      { usage: 'initiative_utility', enabled: true },
      { usage: null, enabled: true },
      { usage: null, enabled: false },
    ]);
    await expectNoOverflow(page, 'jev');
    await section.screenshot({ path: testInfo.outputPath(`jev-${width}.png`) });
    const { blocking, summary } = await scanPage(page, testInfo, `jev-${width}`);
    expect(blocking, summary).toEqual([]);
    await testInfo.attach('browser-errors', {
      body: JSON.stringify({ pageErrors, consoleErrors, unmatchedRequests }),
      contentType: 'application/json',
    });
    expect(pageErrors).toEqual([]);
    expect(unmatchedRequests).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });
}
