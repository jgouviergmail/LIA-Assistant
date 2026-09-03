/**
 * The space page (ADR-259): selecting documents shows the bar; the archive
 * link carries the ids; a move goes through the dialog and reports what moved
 * and what was skipped; a bulk delete asks first and refreshes.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import type { RAGDocument, RAGSpace, RAGSpaceDetail } from '@/types/rag-spaces';

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock('sonner', () => ({ toast }));

const detail = vi.hoisted(() => ({
  space: null as RAGSpaceDetail | null,
  loading: false,
  refetch: vi.fn(),
  setData: vi.fn(),
}));
const list = vi.hoisted(() => ({ spaces: [] as RAGSpace[] }));
vi.mock('@/hooks/useSpaces', () => ({
  useSpaceDetail: () => detail,
  useSpaces: () => ({ spaces: list.spaces, loading: false, error: null, refetch: vi.fn() }),
}));

const docs = vi.hoisted(() => ({
  moveDocuments: vi.fn(),
  bulkDeleteDocuments: vi.fn(),
  deleteDocument: vi.fn(),
  moving: false,
  bulkDeleting: false,
}));
vi.mock('@/hooks/useSpaceDocuments', () => ({
  useSpaceDocuments: () => ({
    uploads: [],
    isUploading: false,
    uploadDocument: vi.fn(),
    deleteDocument: docs.deleteDocument,
    dismissUpload: vi.fn(),
    clearCompletedUploads: vi.fn(),
    deleting: false,
    moveDocuments: docs.moveDocuments,
    bulkDeleteDocuments: docs.bulkDeleteDocuments,
    moving: docs.moving,
    bulkDeleting: docs.bulkDeleting,
    downloadHref: (id: string) => `https://api.test/rag-spaces/s1/documents/${id}/download`,
    archiveHref: (ids: string[]) =>
      `https://api.test/rag-spaces/s1/documents/archive?ids=${ids.join(',')}`,
  }),
}));
vi.mock('@/hooks/useDriveSources', () => ({
  useDriveSources: () => ({
    linkFolder: vi.fn(),
    unlinkFolder: vi.fn(),
    syncFolder: vi.fn(),
    linking: false,
    syncing: false,
  }),
  useDriveFolderBrowser: () => ({
    folders: [],
    files: [],
    loading: false,
    error: null,
    breadcrumb: [{ id: 'root', name: 'Drive' }],
    currentFolderId: 'root',
    navigateToFolder: vi.fn(),
    navigateBack: vi.fn(),
    reset: vi.fn(),
  }),
}));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({ mutate: vi.fn(), loading: false, error: null }),
}));
const push = vi.fn();
vi.mock('@/hooks/useLocalizedRouter', () => ({
  useLocalizedRouter: () => ({ push, replace: vi.fn(), back: vi.fn() }),
}));
const confirm = vi.hoisted(() => ({ answer: true, calls: [] as unknown[] }));
vi.mock('@/components/ui/use-confirm', () => ({
  useConfirm: () => ({
    confirm: async (options: unknown) => {
      confirm.calls.push(options);
      return confirm.answer;
    },
    confirmDialog: null,
  }),
}));

import SpaceDetailPage from '../page';

function document(over: Partial<RAGDocument> = {}): RAGDocument {
  return {
    id: 'd1',
    original_filename: 'report.pdf',
    file_size: 2048,
    content_type: 'application/pdf',
    status: 'ready',
    error_message: null,
    chunk_count: 3,
    embedding_model: 'm',
    embedding_tokens: 0,
    embedding_cost_eur: 0,
    source_type: 'upload',
    drive_file_id: null,
    created_at: '2026-09-02T10:00:00Z',
    ...over,
  };
}

function space(over: Partial<RAGSpace> = {}): RAGSpace {
  return {
    id: 's1',
    name: 'Projets',
    description: null,
    is_active: true,
    document_count: 2,
    ready_document_count: 2,
    total_size: 4096,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    ...over,
  };
}

const ROUTE = { lng: 'en', id: 's1' };
const params = Object.assign(Promise.resolve(ROUTE), { status: 'fulfilled', value: ROUTE });

beforeEach(() => {
  vi.clearAllMocks();
  confirm.answer = true;
  confirm.calls = [];
  detail.space = {
    ...space(),
    documents: [document(), document({ id: 'd2', original_filename: 'notes.md' })],
    drive_sources: [],
  };
  detail.loading = false;
  list.spaces = [space(), space({ id: 's2', name: 'Archives', document_count: 4 })];
  docs.moveDocuments.mockResolvedValue({
    done: ['d1'],
    skipped: [{ id: 'd2', code: 'document_busy' }],
  });
  docs.bulkDeleteDocuments.mockResolvedValue({ done: ['d1', 'd2'], skipped: [] });
});

async function selectBoth(user: ReturnType<typeof renderWithProviders>['user']) {
  await user.click(
    within(screen.getByRole('listitem', { name: 'report.pdf' })).getByRole('checkbox')
  );
  await user.click(
    within(screen.getByRole('listitem', { name: 'notes.md' })).getByRole('checkbox')
  );
}

describe('SpaceDetailPage — selection (ADR-259)', () => {
  it('shows the bar once a row is selected, with the archive link carrying the ids', async () => {
    const { user } = renderWithProviders(<SpaceDetailPage params={params} />);
    expect(screen.queryByRole('region', { name: 'spaces.documents.selection_region' })).toBeNull();
    await selectBoth(user);
    expect(
      screen.getByRole('link', { name: 'spaces.documents.download_selected' })
    ).toHaveAttribute('href', 'https://api.test/rag-spaces/s1/documents/archive?ids=d1,d2');
  });

  it('moves the selection through the dialog and reports moved and skipped', async () => {
    const { user } = renderWithProviders(<SpaceDetailPage params={params} />);
    await selectBoth(user);
    await user.click(screen.getByRole('button', { name: 'spaces.documents.move_selected' }));
    await user.click(
      await screen.findByRole('combobox', { name: 'spaces.documents.move_dialog.target_label' })
    );
    await user.click(await screen.findByRole('option', { name: /Archives/ }));
    await user.click(screen.getByRole('button', { name: 'spaces.documents.move_dialog.submit' }));
    await waitFor(() => expect(docs.moveDocuments).toHaveBeenCalledWith(['d1', 'd2'], 's2'));
    expect(toast.success).toHaveBeenCalledWith('spaces.documents.moved');
    expect(toast.info).toHaveBeenCalledWith('spaces.documents.skipped');
    expect(screen.queryByRole('region', { name: 'spaces.documents.selection_region' })).toBeNull();
  });

  it('deletes the selection after confirmation', async () => {
    const { user } = renderWithProviders(<SpaceDetailPage params={params} />);
    await selectBoth(user);
    await user.click(screen.getByRole('button', { name: 'spaces.documents.delete_selected' }));
    expect(confirm.calls).toHaveLength(1);
    await waitFor(() => expect(docs.bulkDeleteDocuments).toHaveBeenCalledWith(['d1', 'd2']));
    expect(toast.success).toHaveBeenCalledWith('spaces.documents.bulk_deleted');
  });

  it('does nothing when the deletion is declined', async () => {
    confirm.answer = false;
    const { user } = renderWithProviders(<SpaceDetailPage params={params} />);
    await selectBoth(user);
    await user.click(screen.getByRole('button', { name: 'spaces.documents.delete_selected' }));
    expect(docs.bulkDeleteDocuments).not.toHaveBeenCalled();
  });

  it('moves one row from its own action', async () => {
    const { user } = renderWithProviders(<SpaceDetailPage params={params} />);
    const row = screen.getByRole('listitem', { name: 'report.pdf' });
    await user.click(within(row).getByRole('button', { name: 'spaces.documents.move' }));
    await user.click(
      await screen.findByRole('combobox', { name: 'spaces.documents.move_dialog.target_label' })
    );
    await user.click(await screen.findByRole('option', { name: /Archives/ }));
    await user.click(screen.getByRole('button', { name: 'spaces.documents.move_dialog.submit' }));
    await waitFor(() => expect(docs.moveDocuments).toHaveBeenCalledWith(['d1'], 's2'));
  });
});
