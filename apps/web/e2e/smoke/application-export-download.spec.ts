import AxeBuilder from '@axe-core/playwright';
import { test, expect, chatRoutes, waitForHydration } from '../fixtures';

const command = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const conversation = '00000000-0000-4000-8000-00000000c001';
const refs = [{ command_id: command }];
for (const exported of [
  {
    operation: 'meeting_report.download',
    title: 'Compte rendu à télécharger',
    endpoint: 'meeting-pdf',
    filename: 'controlled-meeting.pdf',
    contentType: 'application/pdf',
  },
  {
    operation: 'journals.export',
    title: 'Télécharger le journal',
    endpoint: 'management-export',
    filename: 'lia-journals.json',
    contentType: 'application/json',
  },
  {
    operation: 'account_export.download',
    title: 'Télécharger l’archive du compte',
    endpoint: 'download',
    filename: 'lia-account-export.zip',
    contentType: 'application/zip',
  },
  {
    operation: 'interests.export',
    title: 'Télécharger les centres d’intérêt',
    endpoint: 'management-export',
    filename: 'lia-interests.csv',
    contentType: 'text/csv',
  },
  {
    operation: 'memories.export',
    title: 'Télécharger les mémoires actuelles',
    endpoint: 'management-export',
    filename: 'lia-memories.json',
    contentType: 'application/json',
  },
]) {
  const title = exported.title;

  for (const { width, transferFailure } of [
    { width: 1280, transferFailure: false },
    { width: 320, transferFailure: false },
    { width: 320, transferFailure: true },
  ]) {
    test(`${exported.operation}: exact approval starts one browser download at ${width}px, failed transfer ${transferFailure}`, async ({
      page,
      authenticate,
      mockApi,
      baseURL,
    }) => {
      await page.setViewportSize({ width, height: 900 });
      await authenticate();
      if (!baseURL) throw new Error('An HTTP proof server is required');
      await page.context().addCookies([
        {
          name: 'lia_session',
          value: 'e2e-download-session',
          url: baseURL,
          httpOnly: true,
          sameSite: 'Lax',
        },
      ]);
      await mockApi(chatRoutes([]));
      let confirmed = false;
      let attempts = 0;
      const expires = new Date(Date.now() + 300_000).toISOString();
      await mockApi([
        {
          url: '**/api/v1/agents/hitl/pending',
          handler: async route => {
            await route.fulfill({
              json: confirmed
                ? null
                : {
                    message_id: 'hitl-download-e2e',
                    interrupt_ts: new Date().toISOString(),
                    generated_question:
                      'Confirmer le téléchargement de cette archive personnelle dans le navigateur d’origine ?',
                    action_requests: [
                      {
                        type: 'draft_critique',
                        draft_type: 'application_action',
                        draft_id: 'download-e2e',
                        available_actions: [
                          { action: 'confirm', label: 'confirm', style: 'primary' },
                          { action: 'cancel', label: 'cancel', style: 'destructive' },
                        ],
                        registry_ids: [],
                      },
                    ],
                  },
            });
          },
        },
        {
          url: '**/api/v1/agents/chat/stream',
          method: 'POST',
          handler: async route => {
            const body: { hitl_decision?: { action?: string } } = route.request().postDataJSON();
            expect(body.hitl_decision?.action).toBe('confirm');
            confirmed = true;
            await route.fulfill({
              contentType: 'text/event-stream',
              body:
                'data: {"type":"token","content":"Votre navigateur peut maintenant demander cette archive.","metadata":null}\n\n' +
                `data: ${JSON.stringify({ type: 'done', content: '', metadata: { application_interactions: refs } })}\n\n`,
            });
          },
        },
        {
          url: '**/api/v1/conversations/me/messages*',
          handler: async route => {
            await route.fulfill({
              json: {
                messages: confirmed
                  ? [
                      {
                        id: '00000000-0000-4000-8000-000000001001',
                        role: 'assistant',
                        content: 'Votre navigateur peut maintenant demander cette archive.',
                        created_at: new Date().toISOString(),
                        message_metadata: { application_interactions: refs },
                      },
                    ]
                  : [],
                conversation_id: conversation,
                total_count: confirmed ? 1 : 0,
                has_more: false,
                next_cursor: null,
              },
            });
          },
        },
        {
          url: `**/api/v1/application-commands/${command}`,
          handler: async route => {
            const interaction = { interaction_id: command, kind: 'device', expires_at: expires };
            const phase = attempts ? (transferFailure ? 'failed' : 'committed') : 'waiting';
            const committed = !!attempts && !transferFailure;
            await route.fulfill({
              json: {
                schema_version: 1,
                command_id: command,
                operation_id: exported.operation,
                phase,
                expires_at: expires,
                interaction: attempts ? null : interaction,
                outcome: {
                  success: committed,
                  committed,
                  phase,
                  no_op: false,
                  values: committed
                    ? { export_job_id: command, download_requested: true, save_confirmed: false }
                    : {},
                  error_code: attempts && transferFailure ? 'DEPENDENCY_ERROR' : null,
                  interaction: attempts ? null : interaction,
                },
              },
            });
          },
        },
        {
          url: `**/api/v1/application-commands/${command}/${exported.endpoint}`,
          method: 'GET',
          handler: async route => {
            expect(confirmed).toBe(true);
            expect(route.request().postData()).toBeNull();
            expect((await route.request().allHeaders()).cookie).toContain(
              'lia_session=e2e-download-session'
            );
            attempts += 1;
            if (transferFailure) {
              await route.fulfill({
                status: 503,
                json: { detail: { error_code: 'DEPENDENCY_ERROR' } },
              });
              return;
            }
            await route.fulfill({
              contentType: exported.contentType,
              headers: {
                'Content-Disposition': `attachment; filename="${exported.filename}"`,
                'Cache-Control': 'no-store',
              },
              body: Buffer.from('controlled archive'),
            });
          },
        },
      ]);
      await page.goto('/fr/dashboard/chat');
      await waitForHydration(page, 'section[aria-label="Brouillon à valider"] button');
      expect(attempts).toBe(0);
      await page
        .getByRole('region', { name: 'Brouillon à valider' })
        .getByRole('button', { name: 'Confirmer', exact: true })
        .click();
      const card = page.getByRole('region', { name: title });
      await expect(card).toBeVisible();
      expect(attempts).toBe(0);
      const start = card.getByRole('link', { name: 'Lancer le téléchargement' });
      const downloading = transferFailure ? null : page.waitForEvent('download');
      await start.focus();
      await page.keyboard.press('Enter');
      if (transferFailure) {
        await expect(card).toBeVisible();
        await expect(card.getByRole('status')).toContainText('LIA ne peut pas confirmer');
        expect(attempts).toBe(1);
        await page.keyboard.press('Enter');
        expect(attempts).toBe(1);
        await card.getByRole('button', { name: 'Vérifier le résultat' }).click();
        await expect(card.getByRole('status')).toContainText('L’action n’a pas pu être terminée.');
        expect(
          (await new AxeBuilder({ page }).include(`section[aria-label="${title}"]`).analyze())
            .violations
        ).toEqual([]);
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= document.documentElement.clientWidth
          )
        ).toBe(true);
        return;
      }
      if (!downloading) throw new Error('Missing download expectation');
      const download = await downloading;
      expect(download.suggestedFilename()).toBe(exported.filename);
      expect(await download.failure()).toBeNull();
      expect(attempts).toBe(1);
      await expect(card.getByRole('status')).toContainText('LIA ne peut pas confirmer');
      await expect(page.getByRole('dialog')).toHaveCount(0);
      await page.keyboard.press('Enter');
      expect(attempts).toBe(1);
      await card.getByRole('button', { name: 'Vérifier le résultat' }).click();
      await expect(card.getByRole('status')).toContainText(
        'La demande de téléchargement est enregistrée.'
      );
      expect(
        (await new AxeBuilder({ page }).include(`section[aria-label="${title}"]`).analyze())
          .violations
      ).toEqual([]);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth
        )
      ).toBe(true);
      await page.screenshot({ path: test.info().outputPath(`download-${width}.png`) });
      await page.reload();
      await expect(page.getByRole('region', { name: title }).getByRole('status')).toContainText(
        'La demande de téléchargement est enregistrée.'
      );
      await expect(page.getByRole('link', { name: 'Lancer le téléchargement' })).toHaveCount(0);
      expect(attempts).toBe(1);
    });
  }
}
