/** A slow sync-status poll must preserve the person's current interaction. */
import {
  test,
  expect,
  idleNotificationStream,
  waitForHydration,
  waitForMockGate,
  type MockRoute,
} from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';
import type { RAGDocument, RAGSpaceDetail } from '../../src/types/rag-spaces';

const SPACE_ID = '00000000-0000-4000-8000-00000000bb01';

function document(index: number): RAGDocument {
  return {
    id: `document-${index}`,
    original_filename: `Thread ${index}.md`,
    file_size: 1024,
    content_type: 'text/markdown',
    status: 'ready',
    error_message: null,
    error_code: null,
    chunk_count: 1,
    embedding_model: 'fixture',
    embedding_tokens: 10,
    embedding_cost_eur: 0,
    source_type: 'mail',
    drive_file_id: null,
    mail_thread_id: `thread-${index}`,
    created_at: '2026-11-09T10:00:00Z',
  };
}

const detail: RAGSpaceDetail = {
  id: SPACE_ID,
  name: 'Mail archive',
  description: null,
  is_active: true,
  is_favorite: false,
  kind: null,
  document_count: 30,
  ready_document_count: 30,
  total_size: 30 * 1024,
  created_at: '2026-11-09T10:00:00Z',
  updated_at: '2026-11-09T10:00:00Z',
  documents: Array.from({ length: 30 }, (_, index) => document(index)),
  active_drive: null,
  drive_sources: [],
  mail_sources: [
    {
      id: '00000000-0000-4000-8000-00000000bb02',
      label_id: 'label-fixture',
      label_name: 'Archive',
      sync_status: 'syncing',
      last_sync_at: null,
      thread_count: 31,
      synced_thread_count: 30,
      error_message: null,
      created_at: '2026-11-09T10:00:00Z',
    },
  ],
};

async function mockSyncingSpace(mockApi: (routes: MockRoute[]) => Promise<void>) {
  const gate = Promise.withResolvers<void>();
  let reads = 0;
  await mockApi([
    idleNotificationStream,
    { url: '**/api/v1/notifications/broadcasts/unread', json: { broadcasts: [] } },
    {
      url: '**/api/v1/config',
      json: {
        ...appConfig,
        features: { ...appConfig.features, rag_spaces_mail_sync_enabled: true },
      },
    },
    { url: '**/api/v1/rag-spaces', json: { spaces: [detail], total: 1 } },
    { url: '**/api/v1/rag-spaces?*', json: { spaces: [detail], total: 1 } },
    { url: `**/api/v1/rag-spaces/${SPACE_ID}/mail-labels`, json: { labels: [] } },
    {
      url: `**/api/v1/rag-spaces/${SPACE_ID}`,
      handler: async (route, signal) => {
        reads += 1;
        if (reads > 1 && !(await waitForMockGate(gate.promise, signal))) return;
        const response: RAGSpaceDetail =
          reads === 1
            ? detail
            : {
                ...detail,
                document_count: 31,
                ready_document_count: 31,
                total_size: 31 * 1024,
                documents: [document(30), ...detail.documents],
                mail_sources: detail.mail_sources.map(source => ({
                  ...source,
                  sync_status: 'completed',
                  synced_thread_count: 31,
                })),
              };
        await route.fulfill({ json: response });
      },
    },
  ]);
  return { reads: () => reads, release: () => gate.resolve() };
}

test('Gmail polling preserves selection, focus and scroll during a delayed response', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate({ language: 'en' });
  const sync = await mockSyncingSpace(mockApi);

  try {
    await page.goto(`/en/dashboard/spaces/${SPACE_ID}`);
    await waitForHydration(page, 'main');
    const checkbox = page.getByRole('listitem', { name: 'Thread 15.md' }).getByRole('checkbox');
    // WebKit does not focus a checkbox on pointer click. Establish the same
    // keyboard interaction on every engine before checking focus preservation.
    await checkbox.focus();
    await checkbox.press('Space');
    await expect(checkbox).toBeChecked();
    await expect(checkbox).toBeFocused();
    const position = await checkbox.boundingBox();
    expect(position).not.toBeNull();

    await expect.poll(sync.reads).toBeGreaterThan(1);
    await expect(checkbox).toBeVisible();
    await expect(checkbox).toBeChecked();
    await expect(checkbox).toBeFocused();
    expect((await checkbox.boundingBox())?.y).toBe(position?.y);

    sync.release();
    await expect(page.getByRole('listitem', { name: 'Thread 30.md' })).toBeAttached();
    await expect(checkbox).toBeChecked();
    await expect(checkbox).toBeFocused();
    expect((await checkbox.boundingBox())?.y).toBe(position?.y);
  } finally {
    sync.release();
  }
});

test('Gmail polling preserves an open edit form and its unsaved text', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate({ language: 'en' });
  const sync = await mockSyncingSpace(mockApi);
  try {
    await page.goto(`/en/dashboard/spaces/${SPACE_ID}`);
    await waitForHydration(page, 'main');
    await page.getByRole('button', { name: 'Edit', exact: true }).click();
    const dialog = page.getByRole('dialog');
    const name = dialog.getByRole('textbox', { name: 'Name', exact: true });
    const description = dialog.getByRole('textbox', { name: /^Description/ });
    await name.fill('Unfinished name');
    await description.fill('Unfinished description');

    await expect.poll(sync.reads).toBeGreaterThan(1);
    await expect(dialog).toBeVisible();
    await expect(description).toBeFocused();
    await expect(name).toHaveValue('Unfinished name');

    sync.release();
    await expect(
      page.getByRole('listitem', { name: 'Thread 30.md', includeHidden: true })
    ).toBeAttached();
    await expect(name).toHaveValue('Unfinished name');
    await expect(description).toHaveValue('Unfinished description');
    await expect(description).toBeFocused();

    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(dialog).not.toBeVisible();
    await page.getByRole('button', { name: 'Edit', exact: true }).click();
    await expect(name).toHaveValue(detail.name);
    await expect(description).toHaveValue('');
  } finally {
    sync.release();
  }
});
