/**
 * Importing a meeting from a file (owner request 2026-10-24), on a desktop and on
 * a phone.
 *
 * Unit tests cover the bounds, the chunking and the dialog; the browser proves
 * the journey through the real page and the real upload code: the « Import »
 * action of the meetings page opens the dialog, a voice memo is chosen, the
 * import is opened with what the file says, its bytes travel as raw chunks of
 * the size the server published — in order — and once the server took them all
 * the meeting's own page opens, marked « Imported ».
 */
import { test, expect, waitForHydration } from '../fixtures';
import { MEETING_ID, SIZE, meetingImportRoutes, voiceMemo } from '../fixtures/meeting-import';

for (const [device, viewport] of [
  ['desktop', { width: 1280, height: 900 }],
  ['phone', { width: 375, height: 812 }],
] as const) {
  test(`imports a voice memo as a meeting and opens it (${device})`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize(viewport);
    const sent: number[] = [];
    const opened: unknown[] = [];
    const completed: unknown[] = [];
    await authenticate({ language: 'fr' });
    await mockApi(meetingImportRoutes(sent, opened, completed));

    await page.goto('/fr/dashboard/meetings');
    await waitForHydration(page, 'h1');
    await page.getByRole('button', { name: 'Importer', exact: true }).click();

    const dialog = page.getByRole('dialog', { name: 'Importer un enregistrement' });
    await expect(dialog).toBeVisible();
    await dialog.getByLabel('Fichier audio').setInputFiles({
      name: 'memo.m4a',
      mimeType: 'audio/mp4',
      buffer: voiceMemo(),
    });
    await expect(dialog.getByText(/memo\.m4a/)).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
    ).toBe(true);
    await dialog.getByRole('button', { name: 'Importer', exact: true }).click();

    await expect(page).toHaveURL(new RegExp(`/dashboard/meetings/${MEETING_ID}$`));
    await expect(page.getByText('Importé', { exact: true })).toBeVisible();
    expect(opened).toEqual([
      expect.objectContaining({ audio_format: 'import_m4a', size_bytes: SIZE, language: 'auto' }),
    ]);
    // The chunks the server published, in order, then ONE completion.
    expect(sent).toEqual([0, 1, 2]);
    expect(completed).toEqual([{ chunk_count: 3 }]);
  });
}
