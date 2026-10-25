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
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';
import { meetingDetail } from '../../src/__tests__/fixtures/meeting-detail';

const MEETING_ID = '7b0d4b62-3c0a-4b8f-9b8e-2f6d1c4a9e10';
const CHUNK = 1024;
const SIZE = 2500;

function routes(sent: number[], opened: unknown[], completed: unknown[]): MockRoute[] {
  return [
    {
      url: '**/api/v1/config',
      json: {
        sse: { heartbeat_interval_seconds: 30 },
        rate_limits: { enabled: false, per_minute: 60, burst: 10 },
        i18n: {
          supported_languages: ['en', 'fr', 'de', 'es', 'it', 'zh'],
          default_language: 'fr',
        },
        features: { meetings_enabled: true, meetings_import_enabled: true },
        api_version: 'v1',
      },
    },
    { url: '**/api/v1/notifications/broadcasts/unread', json: { broadcasts: [] } },
    // The REAL contract (`MeetingListResponse`): `items`, not `meetings`.
    { url: '**/api/v1/meetings**', json: { items: [], total: 0, limit: 20, offset: 0 } },
    // AFTER the catch-all above: Playwright answers with the LAST matching route.
    { url: '**/api/v1/meetings/templates', json: { items: [], max_user_templates: 50 } },
    {
      url: '**/api/v1/meetings/imports/limits',
      json: { max_bytes: 10_000, chunk_max_bytes: CHUNK, max_duration_minutes: 180 },
    },
    {
      url: '**/api/v1/meetings/imports',
      method: 'POST',
      handler: async route => {
        opened.push(route.request().postDataJSON());
        await route.fulfill({
          status: 201,
          json: {
            id: MEETING_ID,
            status: 'uploading',
            started_at: '2026-10-20T09:00:00Z',
            engine: { provider: 'local', model: null, diarized: false },
            limits: { max_bytes: 10_000, chunk_max_bytes: CHUNK, max_duration_minutes: 180 },
          },
        });
      },
    },
    {
      url: new RegExp(`/api/v1/meetings/${MEETING_ID}/import/\\d+$`),
      method: 'PUT',
      handler: async route => {
        const sequence = Number(route.request().url().split('/').pop());
        sent.push(sequence);
        await route.fulfill({
          json: {
            sequence,
            segment_count: sequence + 1,
            audio_bytes: 0,
            status: 'uploading',
          },
        });
      },
    },
    {
      url: `**/api/v1/meetings/${MEETING_ID}/import/complete`,
      method: 'POST',
      handler: async route => {
        completed.push(route.request().postDataJSON());
        await route.fulfill({
          status: 202,
          json: { id: MEETING_ID, status: 'stopped', stage: null },
        });
      },
    },
    {
      url: `**/api/v1/meetings/${MEETING_ID}`,
      method: 'GET',
      json: meetingDetail({
        id: MEETING_ID,
        status: 'stopped',
        audio_format: 'import_m4a',
        report: null,
      }),
    },
  ];
}

/** An M4A as a phone writes it: `ftyp` at offset 4, then bytes. */
function voiceMemo(): Buffer {
  const head = Buffer.from([0, 0, 0, 0x1c, ...Buffer.from('ftypM4A ')]);
  return Buffer.concat([head, Buffer.alloc(SIZE - head.length, 1)]);
}

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
    await mockApi(routes(sent, opened, completed));

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
