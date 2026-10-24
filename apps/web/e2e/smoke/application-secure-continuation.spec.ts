import AxeBuilder from '@axe-core/playwright';
import { test, expect, chatRoutes, waitForHydration } from '../fixtures';

const command = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const conversation = '00000000-0000-4000-8000-00000000c001';
const refs = [{ command_id: command }];

function observation(complete: boolean, exporting = false) {
  const expires = new Date(Date.now() + 300_000).toISOString();
  const interaction = { interaction_id: command, kind: 'secure' as const, expires_at: expires };
  return {
    schema_version: 1, command_id: command, operation_id: exporting ? 'account_export.request' : 'device_sessions.revoke_others',
    phase: complete ? 'committed' : 'waiting', expires_at: expires,
    interaction: complete ? null : interaction,
    outcome: complete ? {
      success: true, committed: true, phase: 'committed', no_op: false,
      values: exporting ? { export_job_id: command, export_status: 'pending' } : { revoked_sessions: 2, approved_sessions: 2 }, error_code: null, interaction: null,
    } : {
      success: false, committed: false, phase: 'waiting', no_op: false,
      values: {}, error_code: null, interaction,
    },
  };
}

for (const { width, lostResponse, exporting } of [
  { width: 1280, lostResponse: false, exporting: false },
  { width: 320, lostResponse: false, exporting: false },
  { width: 320, lostResponse: true, exporting: false },
  { width: 320, lostResponse: false, exporting: true },
]) {
  test(`confirmed secure action survives reload at ${width}px, lost response ${lostResponse}, export ${exporting}`, async ({ page, authenticate, mockApi }) => {
    const title = exporting ? 'Terminer la demande d’export du compte' : 'Terminer la déconnexion des autres sessions';
    const completed = exporting ? 'Export demandé. Sa préparation se poursuit en arrière-plan ; consulte son état dans les réglages.' : '2 sessions déconnectées.';
    await page.setViewportSize({ width, height: 900 });
    await authenticate();
    await mockApi(chatRoutes([]));
    let confirmed = false;
    let verified = lostResponse;
    let complete = false;
    let attempts = 0;
    await mockApi([
      { url: '**/api/v1/agents/hitl/pending', handler: async route => {
        await route.fulfill({ json: confirmed ? null : {
          message_id: 'hitl-secure-e2e', interrupt_ts: new Date().toISOString(),
          generated_question: exporting ? 'Confirmer la demande d’export complet du compte ? L’archive contiendra vos données personnelles.' : 'Confirmer la déconnexion des deux autres sessions ? La session actuelle sera conservée.',
          action_requests: [{ type: 'draft_critique', draft_type: 'application_action', draft_id: 'secure-e2e',
            available_actions: [{ action: 'confirm', label: 'confirm', style: 'primary' }, { action: 'cancel', label: 'cancel', style: 'destructive' }], registry_ids: [] }],
        } });
      } },
      { url: '**/api/v1/agents/chat/stream', method: 'POST', handler: async route => {
        const body: { hitl_decision?: { action?: string } } = route.request().postDataJSON();
        expect(body.hitl_decision?.action).toBe('confirm');
        confirmed = true;
        await route.fulfill({ contentType: 'text/event-stream', body:
          'data: {"type":"token","content":"L’action attend votre réauthentification sécurisée.","metadata":null}\n\n' +
          `data: ${JSON.stringify({ type: 'done', content: '', metadata: { application_interactions: refs } })}\n\n`,
        });
      } },
      { url: '**/api/v1/conversations/me/messages*', handler: async route => {
        await route.fulfill({ json: { messages: confirmed ? [{
          id: '00000000-0000-4000-8000-000000001001', role: 'assistant',
          content: 'L’action attend votre réauthentification sécurisée.', created_at: new Date().toISOString(),
          message_metadata: { application_interactions: refs },
        }] : [], conversation_id: conversation, total_count: confirmed ? 1 : 0, has_more: false, next_cursor: null } });
      } },
      { url: `**/api/v1/application-commands/${command}`, handler: async route => { await route.fulfill({ json: observation(complete, exporting) }); } },
      { url: `**/api/v1/application-commands/${command}/resume`, method: 'POST', handler: async route => {
        expect(confirmed).toBe(true);
        expect(route.request().postData()).toBeNull();
        attempts += 1;
        if (!verified) await route.fulfill({ status: 403, json: { detail: { error: 'step_up_required' } } });
        else {
          complete = true;
          if (lostResponse) await route.abort('connectionreset');
          else await route.fulfill({ json: observation(true, exporting) });
        }
      } },
      { url: '**/api/v1/auth/step-up/status', json: { methods: ['password'], password_set: true, step_up_valid_until: null, password_recovery: 'email_link', sign_in_provider: null } },
      { url: '**/api/v1/auth/step-up/password', method: 'POST', handler: async route => {
        verified = true; await route.fulfill({ json: { verified: true } });
      } },
    ]);
    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page, 'section[aria-label="Brouillon à valider"] button');
    expect(attempts).toBe(0);
    const approval = page.getByRole('region', { name: 'Brouillon à valider' });
    await approval.getByRole('button', { name: 'Confirmer', exact: true }).click();
    const card = page.getByRole('region', { name: title });
    await expect(card).toBeVisible();
    expect(attempts).toBe(0);
    const proceed = card.getByRole('button', { name: 'Poursuivre en sécurité' });
    await proceed.focus(); await page.keyboard.press('Enter');
    if (lostResponse) {
      await expect(card.getByRole('status')).toHaveText('Le résultat n’est pas encore confirmé. Vérifie-le sans soumettre à nouveau l’action.');
      await expect(card.getByRole('button', { name: 'Poursuivre en sécurité' })).toHaveCount(0);
      await card.getByRole('button', { name: 'Vérifier le résultat' }).click();
    } else {
      const dialog = page.getByRole('dialog');
      await expect(dialog).toBeVisible();
      await dialog.locator('input[type="password"]').fill('e2e-placeholder-password');
      await dialog.getByRole('button', { name: /Vérifier/i }).click();
    }
    await expect(card.getByRole('status')).toHaveText(completed);
    await expect(card.getByRole('button', { name: 'Vérifier le résultat' })).toBeFocused();
    expect(attempts).toBe(lostResponse ? 1 : 2);
    expect((await new AxeBuilder({ page }).include(`section[aria-label="${title}"]`).analyze()).violations).toEqual([]);
    const fits = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);
    expect(fits).toBe(true);
    await page.screenshot({ path: test.info().outputPath(`secure-${width}.png`) });
    await page.reload();
    await expect(page.getByRole('region', { name: title }).getByRole('status')).toHaveText(completed);
    expect(attempts).toBe(lostResponse ? 1 : 2);
  });
}
