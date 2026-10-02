/** Native background calls remain observable independently of chat history. */
import { test, expect, chatRoutes, idleNotificationStream } from '../fixtures';
import type { JevCallTrace } from '../../src/types/jev';
import { scanPage } from '../a11y/scan';

for (const lng of ['en', 'fr'] as const) {
  test(`JEV diagnostics are readable, bounded and revocable (${lng})`, async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    const errors: string[] = [];
    const unmatched: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('response', response => {
      if (response.status() === 501) unmatched.push(new URL(response.url()).pathname);
    });
    await authenticate({ language: lng, is_superuser: true });
    let reads = 0;
    let denied = false;
    const trace: JevCallTrace = {
      id: 'native-call',
      run_id: 'background-meeting-run',
      caller: 'meeting_template_selection',
      usage: 'meeting_template',
      started_at: '2026-09-28T12:00:00Z',
      requested_model: 'jev-1.13.0',
      reported_model: 'jev-1.13.0',
      duration_ms: 255,
      context: {
        text: '<script>window.jevInjected=true</script>\n' + 'Contexte synthétique 界 '.repeat(260),
        original_characters: 19000,
        omitted_characters: 13000,
      },
      response: {
        choice: 'c1',
        choice_label: 'Consultation médicale',
        confidence: 0.7,
        probabilities: [{ key: 'c1', label: 'Consultation médicale', probability: 0.7 }],
        omitted_candidates: 0,
      },
      outcome: 'low_confidence',
      action: 'fallback',
      action_target: 'meeting_synthesis',
      status_code: null,
      input_tokens: 300,
      output_tokens: 2,
      cost_eur: 0.00001134,
    };
    await mockApi([
      ...chatRoutes([]),
      { url: '**/api/v1/habits/presence', json: {} },
      { url: '**/api/v1/telephony/calls*', json: { calls: [], total: 0 } },
      { url: '**/api/v1/conversations/me', json: { id: '00000000-0000-4000-8000-0000000000ff' } },
      { url: '**/api/v1/notifications/broadcasts/unread', json: { broadcasts: [] } },
      idleNotificationStream,
      { url: '**/api/v1/briefing/companion-context', json: { timezone: 'UTC', weather: null } },
      { url: '**/api/v1/psyche/settings', json: { enabled: false } },
      { url: '**/api/v1/skills*', json: { skills: [] } },
      { url: '**/api/v1/chat/shortcuts*', json: { shortcuts: [] } },
      { url: '**/api/v1/chat/suggestions*', json: { suggestions: [] } },
      {
        url: '**/api/v1/system-settings/debug-panel-status',
        json: { enabled: true, user_access_available: false },
      },
      {
        url: '**/api/v1/debug/jev',
        handler: async route => {
          reads++;
          await route.fulfill(
            denied
              ? { status: 403, json: { detail: 'Permission denied' } }
              : { json: { calls: [trace], limit: 30, retention_seconds: 3600 } }
          );
        },
      },
    ]);
    await page.goto(`/${lng}/dashboard/chat`);
    const toggle = page.getByRole('button', {
      name: lng === 'fr' ? 'Appels JEV' : 'JEV calls',
      exact: true,
    });
    await expect(toggle).toBeVisible({ timeout: 60_000 });
    expect(reads).toBe(0);
    await toggle.focus();
    await page.keyboard.press('Enter');
    await page
      .getByText(lng === 'fr' ? 'Détails techniques' : 'Technical details', { exact: true })
      .click();
    await expect(page.getByText('background-meeting-run', { exact: true })).toBeVisible();
    const article = page.getByRole('article').filter({ hasText: 'background-meeting-run' });
    await expect(
      article.getByText(
        lng === 'fr' ? 'Traitement existant sollicité' : 'Existing processing requested'
      )
    ).toBeVisible();
    await article
      .getByText(lng === 'fr' ? 'Contexte envoyé' : 'Submitted context', { exact: true })
      .click();
    await expect(article.locator('pre')).toContainText('<script>');
    const context = article.getByRole('region', {
      name: lng === 'fr' ? 'Contexte envoyé' : 'Submitted context',
    });
    await context.focus();
    await page.keyboard.press('PageDown');
    await expect.poll(() => context.evaluate(element => element.scrollTop)).toBeGreaterThan(0);
    expect(await page.evaluate(() => 'jevInjected' in window)).toBe(false);
    await expect(article.getByText(/13000/)).toBeVisible();
    // Exercise the real resizable panel at its narrowest width.
    const splitter = page.getByRole('separator');
    await splitter.focus();
    await page.keyboard.press('Home');
    expect(await article.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(
      true
    );
    await article
      .getByText(lng === 'fr' ? 'Contexte envoyé' : 'Submitted context', { exact: true })
      .click();
    await article
      .getByText(lng === 'fr' ? 'Détails techniques' : 'Technical details', { exact: true })
      .click();
    await article.getByRole('heading').first().scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath(`jev-debug-${lng}.png`) });
    const { blocking, summary } = await scanPage(page, testInfo, `jev-debug-${lng}`);
    expect(blocking, summary).toEqual([]);
    const refresh = page.getByRole('button', {
      name: lng === 'fr' ? 'Actualiser' : 'Refresh',
      exact: true,
    });
    denied = true;
    await refresh.focus();
    await page.keyboard.press('Enter');
    await expect(
      page.getByRole('alert').filter({ hasText: lng === 'fr' ? 'accès retiré' : 'access removed' })
    ).toBeVisible();
    await expect(page.getByText('background-meeting-run')).toHaveCount(0);
    await expect(refresh).toBeFocused();
    denied = false;
    trace.action = 'observed';
    trace.usage = 'observe_journal';
    trace.observed_result = {
      text: '{"action":"create","content":"Synthetic journal proposal"}',
      original_characters: 65,
      omitted_characters: 0,
    };
    await page.keyboard.press('Enter');
    await expect(
      page.getByText(lng === 'fr' ? 'Observation uniquement' : 'Observation only', { exact: true })
    ).toBeVisible();
    await page
      .getByText(
        lng === 'fr'
          ? 'Proposition de l’extracteur existant (avant validation)'
          : 'Existing extractor proposal (before validation)',
        { exact: true }
      )
      .click();
    await expect(page.getByText('Synthetic journal proposal', { exact: true })).toBeVisible();
    await page
      .getByText(lng === 'fr' ? 'Détails techniques' : 'Technical details', { exact: true })
      .click();
    await expect(page.getByText('background-meeting-run', { exact: true })).toBeVisible();
    await toggle.click();
    await expect(page.getByText('background-meeting-run')).toHaveCount(0);
    expect(errors).toEqual([]);
    expect(unmatched).toEqual([]);
  });
}
