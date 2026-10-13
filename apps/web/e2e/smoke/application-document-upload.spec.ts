import AxeBuilder from '@axe-core/playwright';
import { test, expect, chatRoutes, expectMultipartFile, waitForHydration } from '../fixtures';

const command = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const space = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const conversation = '00000000-0000-4000-8000-00000000c001';

for (const { width, lost } of [{ width: 1280, lost: false }, { width: 320, lost: false }, { width: 320, lost: true }]) {
  test(`confirmed local document uploads once at ${width}px, lost response ${lost}`, async ({ page, authenticate, mockApi, browserName }) => {
    await page.setViewportSize({ width, height: 900 });
    await authenticate(); await mockApi(chatRoutes([]));
    let attempts = 0; let accepted = false;
    const expires = new Date(Date.now() + 300_000).toISOString();
    const interaction = { interaction_id: command, kind: 'device', expires_at: expires };
    const receipt = { success: true, phase: 'committed', committed: true, no_op: false, error_code: null, interaction: null,
      values: { document_id: command, space_id: space, upload_accepted: true, status: 'pending', indexing_completed: false } };
    await mockApi([
      { url: '**/api/v1/conversations/me/messages*', handler: async route => { await route.fulfill({ json: {
        messages: [{ id: '00000000-0000-4000-8000-000000001001', role: 'assistant', content: 'La destination est confirmée. Choisissez le fichier dans ce navigateur.',
          created_at: new Date().toISOString(), message_metadata: { application_interactions: [{ command_id: command }] } }],
        conversation_id: conversation, total_count: 1, has_more: false, next_cursor: null,
      } }); } },
      { url: `**/api/v1/application-commands/${command}`, handler: async route => { await route.fulfill({ json: {
        schema_version: 1, command_id: command, operation_id: 'knowledge_document.upload', phase: accepted ? 'committed' : 'waiting',
        expires_at: expires, interaction: accepted ? null : interaction, outcome: accepted ? receipt : {
          success: false, phase: 'waiting', committed: false, no_op: false, error_code: null, interaction,
          values: { document_to_upload: { space: { id: space, name: 'Corpus personnel', description: null, is_active: true, kind: null },
            document_count: 1, max_documents: 200, max_file_size_bytes: 20 * 1024 * 1024, allowed_content_types: ['text/plain'],
            browser_file_confirmation_required: true, indexing_requested: true, indexing_cost_may_apply: true } },
        },
      } }); } },
    ]);
    await page.route(`**/api/rag-upload/${space}?application_command=${command}`, async route => {
      attempts += 1;
      expect(route.request().headers()['x-lia-file-confirmed']).toBe('true');
      expectMultipartFile(route.request(), browserName, { name: 'controlled.txt', content: 'controlled document' });
      accepted = true;
      if (lost) await route.abort('failed');
      else await route.fulfill({ json: receipt });
    });
    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page, 'section[aria-label="Importer un document"]');
    const card = page.getByRole('region', { name: 'Importer un document' });
    await expect(card).toBeVisible();
    expect((await new AxeBuilder({ page }).include('section[aria-label="Importer un document"]').analyze()).violations).toEqual([]);
    await page.screenshot({ path: test.info().outputPath(`document-upload-waiting-${width}-${lost}.png`) });
    await card.getByLabel('Choisir un document local').setInputFiles({ name: 'controlled.txt', mimeType: 'text/plain', buffer: Buffer.from('controlled document') });
    expect(attempts).toBe(0);
    const confirm = card.getByRole('button', { name: 'Importer ce document' });
    await confirm.focus(); await page.keyboard.press('Enter');
    if (lost) {
      await expect(card.getByText('Le résultat n’est pas encore confirmé. Vérifiez-le sans soumettre à nouveau l’action.')).toBeVisible();
      await expect(confirm).toHaveAttribute('aria-disabled', 'true');
      await confirm.focus();
      await page.keyboard.press('Enter');
      expect(attempts).toBe(1);
      await card.getByRole('button', { name: 'Vérifier le résultat' }).focus();
      await page.keyboard.press('Enter');
    }
    await expect(card.getByText('Document importé. Indexation en attente.')).toBeVisible();
    await expect(card.getByRole('button', { name: 'Vérifier le résultat' })).toBeFocused();
    expect(attempts).toBe(1);
    expect((await new AxeBuilder({ page }).include('section[aria-label="Importer un document"]').analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    await page.screenshot({ path: test.info().outputPath(`document-upload-${width}-${lost}.png`) });
    await page.reload();
    await expect(page.getByRole('region', { name: 'Importer un document' }).getByText('Document importé. Indexation en attente.')).toBeVisible();
    expect(attempts).toBe(1);
  });
}
