/**
 * Knowledge space — a Drive sync is preceded by its exact count.
 *
 * A linked folder is synchronised WITH its sub-folders, so one click may
 * index far more than the folder shows. Hermetic, in a real engine: the sync
 * button asks the preflight; past the published threshold an alert dialog
 * states the exact figures, « Cancel » starts nothing, « Index them » posts
 * the sync; under the threshold the sync posts at once with no dialog.
 */
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';

const SPACE_ID = '00000000-0000-4000-8000-0000000000d1';
const SOURCE_ID = '00000000-0000-4000-8000-0000000000d2';

const APP_CONFIG = {
  sse: { heartbeat_interval_seconds: 15 },
  rate_limits: { enabled: false, per_minute: 60, burst: 10 },
  i18n: { supported_languages: ['fr', 'en'], default_language: 'fr' },
  features: {
    tool_approval_enabled: true,
    attachments_enabled: true,
    rag_spaces_enabled: true,
    rag_spaces_drive_sync_enabled: true,
    rag_spaces_mail_sync_enabled: false,
    rag_spaces_embedding_model: 'e',
  },
  api_version: 'v1',
};

const SPACE_DETAIL = {
  id: SPACE_ID,
  name: 'Contrats',
  description: null,
  is_active: true,
  kind: null,
  document_count: 0,
  ready_document_count: 0,
  total_size: 0,
  created_at: '2026-09-17T09:00:00Z',
  updated_at: '2026-09-17T09:00:00Z',
  documents: [],
  drive_sources: [
    {
      id: SOURCE_ID,
      folder_id: 'folder-abc',
      folder_name: 'Rapports',
      sync_status: 'idle',
      last_sync_at: null,
      file_count: 0,
      synced_file_count: 0,
      error_message: null,
      created_at: '2026-09-17T09:00:00Z',
    },
  ],
  mail_sources: [],
};

function preflight(over: Record<string, unknown>) {
  return {
    total_files: 37,
    unsupported: 4,
    unchanged: 8,
    modified: 5,
    new: 20,
    over_capacity: 0,
    to_index: 25,
    folders: 4,
    unreadable_folders: 0,
    truncated: false,
    threshold: 10,
    max_files: 500,
    max_folders: 200,
    requires_confirmation: true,
    ...over,
  };
}

function routes(report: Record<string, unknown>, syncs: string[]): MockRoute[] {
  return [
    { url: '**/api/v1/config', json: APP_CONFIG },
    { url: `**/api/v1/rag-spaces/${SPACE_ID}/drive-sources/${SOURCE_ID}/preflight`, json: report },
    {
      url: `**/api/v1/rag-spaces/${SPACE_ID}/drive-sources/${SOURCE_ID}/sync`,
      method: 'POST',
      handler: async route => {
        syncs.push(route.request().url());
        await route.fulfill({
          status: 202,
          contentType: 'application/json',
          body: JSON.stringify({
            sync_status: 'syncing',
            last_sync_at: null,
            file_count: 0,
            synced_file_count: 0,
            error_message: null,
          }),
        });
      },
    },
    { url: `**/api/v1/rag-spaces/${SPACE_ID}`, json: SPACE_DETAIL },
    { url: '**/api/v1/rag-spaces', json: { spaces: [SPACE_DETAIL], total: 1 } },
    { url: '**/api/v1/rag-spaces?*', json: { spaces: [SPACE_DETAIL], total: 1 } },
  ];
}

async function openSpace(page: import('@playwright/test').Page): Promise<void> {
  await page.goto(`/fr/dashboard/spaces/${SPACE_ID}`);
  // The space page has no <form>: hydration is awaited on the main region.
  await waitForHydration(page, 'main');
  await expect(page.getByText('Rapports')).toBeVisible({ timeout: 15_000 });
}

/** The sync action: a button on a wide screen, an item of the row menu on a phone. */
async function clickSync(page: import('@playwright/test').Page): Promise<void> {
  const button = page.getByRole('button', { name: 'Synchroniser' });
  if (await button.isVisible()) {
    await button.click();
    return;
  }
  await page.getByRole('button', { name: /Actions — Rapports/ }).click();
  await page.getByRole('menuitem', { name: 'Synchroniser' }).click();
}

test.describe('Drive sync confirmation', () => {
  test('past the threshold: the exact count, cancel starts nothing, confirm posts the sync', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    const syncs: string[] = [];
    await mockApi(routes(preflight({}), syncs));
    await openSpace(page);

    await clickSync(page);
    const dialog = page.getByRole('alertdialog');
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText('25 fichiers vont être indexés');
    await expect(dialog).toContainText('20 nouveaux, 5 modifiés, 8 déjà à jour, 4 non pris en charge');
    await expect(dialog).toContainText('4 dossiers');
    expect(syncs).toHaveLength(0);

    // Keyboard: Escape cancels, nothing is posted.
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    expect(syncs).toHaveLength(0);

    await clickSync(page);
    await expect(page.getByRole('alertdialog')).toBeVisible();
    await page.getByRole('button', { name: 'Les indexer' }).click();
    await expect.poll(() => syncs.length).toBe(1);
    await expect(page.getByRole('alertdialog')).toBeHidden();
  });

  test('under the threshold: the sync posts at once, no dialog', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    const syncs: string[] = [];
    await mockApi(routes(preflight({ to_index: 3, requires_confirmation: false }), syncs));
    await openSpace(page);

    await clickSync(page);
    await expect.poll(() => syncs.length).toBe(1);
    await expect(page.getByRole('alertdialog')).toHaveCount(0);
  });

  test('a cut walk says « au moins » — 390 px', async ({ page, authenticate, mockApi }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await authenticate({ language: 'fr' });
    const syncs: string[] = [];
    await mockApi(routes(preflight({ truncated: true, to_index: 500 }), syncs));
    await openSpace(page);

    await clickSync(page);
    const dialog = page.getByRole('alertdialog');
    await expect(dialog).toContainText('500 fichiers vont être indexés');
    await expect(dialog).toContainText('Au moins');
    const box = await dialog.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x + box!.width).toBeLessThanOrEqual(390);
  });
});
