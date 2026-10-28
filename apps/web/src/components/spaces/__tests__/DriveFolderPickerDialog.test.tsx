/**
 * DriveFolderPickerDialog — the Drive listing belongs to the picker's opening.
 *
 * The dialog stays mounted while closed (DriveSourcesList keeps it), which is
 * how two defects shipped: a closed picker read Drive on every page load, and
 * a reopened one showed an empty root without asking again. And its retry only
 * re-selected the breadcrumb position it was already on, so it sent nothing.
 *
 * Driven through the production mount, over a transport whose every answer the
 * test releases by hand: a late answer must never reach the screen once the
 * picker closed, moved or retried past it.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { act, fireEvent, renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { DriveFolder, DriveFolderBrowseResponse, RAGDriveSource } from '@/types/rag-spaces';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get },
}));

import { DriveSourcesList } from '../DriveSourcesList';

const FOLDER_MIME = 'application/vnd.google-apps.folder';
const LINK = 'spaces.drive.link_folder';
const LOADING = 'spaces.drive.picker_loading';
const FAILURE = 'spaces.drive.picker_error';
const EMPTY = 'spaces.drive.picker_empty';
const ROOT = 'spaces.drive.picker_root';
const RETRY = 'errors.try_again';
const CANCEL = 'common.cancel';
const SELECT = 'spaces.drive.picker_select';

/** One listing request, answered when the test says so. */
interface BrowseRead {
  folderId: string;
  signal: AbortSignal;
  answer: (files: DriveFolder[]) => Promise<void>;
  fail: () => Promise<void>;
}

let reads: BrowseRead[];

function folder(id: string, name: string): DriveFolder {
  return { id, name, mimeType: FOLDER_MIME, modifiedTime: '2026-10-01T09:00:00Z' };
}

function file(id: string, name: string): DriveFolder {
  return { id, name, mimeType: 'application/pdf', modifiedTime: '2026-10-01T09:00:00Z' };
}

const REPORTS = folder('folder-reports', 'Reports');

function renderList(onLink = vi.fn().mockResolvedValue(undefined)) {
  const sources: RAGDriveSource[] = [];
  const utils = renderWithProviders(
    <DriveSourcesList
      spaceId="space-1"
      sources={sources}
      onLink={onLink}
      onUnlink={vi.fn()}
      onSync={vi.fn()}
    />
  );
  return { ...utils, onLink };
}

/** The read the picker sent most recently, once it has been sent. */
async function nextRead(count: number): Promise<BrowseRead> {
  await waitFor(() => expect(reads).toHaveLength(count));
  return reads[count - 1];
}

function open() {
  fireEvent.click(screen.getByRole('button', { name: LINK }));
}

beforeEach(() => {
  reads = [];
  get.mockReset();
  get.mockImplementation(
    (_endpoint: string, config: { params: { folder_id: string }; signal: AbortSignal }) =>
      new Promise<DriveFolderBrowseResponse>((resolve, reject) => {
        reads.push({
          folderId: config.params.folder_id,
          signal: config.signal,
          answer: files =>
            act(async () => {
              resolve({ files, nextPageToken: null });
            }),
          fail: () =>
            act(async () => {
              reject(new Error('502'));
            }),
        });
      })
  );
});

describe('DriveFolderPickerDialog — the listing belongs to the opening', () => {
  it('asks Drive nothing while the picker is closed', async () => {
    renderList();
    await act(async () => {});

    expect(get).not.toHaveBeenCalled();
  });

  it('shows the loading state from the first frame, then the root', async () => {
    renderList();
    open();

    expect(screen.getByRole('status', { name: LOADING })).toBeInTheDocument();
    expect(screen.queryByText(EMPTY)).not.toBeInTheDocument();

    const root = await nextRead(1);
    expect(root.folderId).toBe('root');
    expect(get).toHaveBeenCalledWith(
      '/rag-spaces/space-1/drive-browse',
      expect.objectContaining({ params: { folder_id: 'root' } })
    );
    await root.answer([REPORTS, file('file-1', 'notes.pdf')]);

    expect(screen.getByRole('button', { name: 'Reports' })).toBeInTheDocument();
    expect(screen.getByText('notes.pdf')).toBeInTheDocument();
    // The root carries no Drive name: it is the translated label.
    expect(screen.getByRole('button', { name: ROOT })).toBeDisabled();
  });

  it('reads the root again at every opening instead of showing it empty', async () => {
    renderList();
    open();
    await (await nextRead(1)).answer([REPORTS]);
    fireEvent.click(screen.getByRole('button', { name: CANCEL }));

    open();

    expect(screen.getByRole('status', { name: LOADING })).toBeInTheDocument();
    expect(screen.queryByText(EMPTY)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reports' })).not.toBeInTheDocument();
    const again = await nextRead(2);
    expect(again.folderId).toBe('root');
    await again.answer([folder('folder-archive', 'Archive')]);
    expect(screen.getByRole('button', { name: 'Archive' })).toBeInTheDocument();
  });

  it('reopens at the root after a sub-folder was left open', async () => {
    renderList();
    open();
    await (await nextRead(1)).answer([REPORTS]);
    fireEvent.click(screen.getByRole('button', { name: 'Reports' }));
    const reports = await nextRead(2);
    expect(reports.folderId).toBe('folder-reports');
    await reports.answer([file('file-2', 'q3.pdf')]);
    fireEvent.click(screen.getByRole('button', { name: CANCEL }));

    open();

    const root = await nextRead(3);
    expect(root.folderId).toBe('root');
    expect(screen.queryByRole('button', { name: 'Reports' })).not.toBeInTheDocument();
    expect(screen.queryByText('q3.pdf')).not.toBeInTheDocument();
  });

  it('links the folder it shows, then reopens at the root', async () => {
    const { onLink } = renderList();
    open();
    await (await nextRead(1)).answer([REPORTS]);
    fireEvent.click(screen.getByRole('button', { name: 'Reports' }));
    await (await nextRead(2)).answer([]);

    fireEvent.click(screen.getByRole('button', { name: SELECT }));

    expect(onLink).toHaveBeenCalledWith('folder-reports', 'Reports');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    open();
    expect((await nextRead(3)).folderId).toBe('root');
  });

  it('links the root under its translated name', async () => {
    const { onLink } = renderList();
    open();
    await (await nextRead(1)).answer([]);

    fireEvent.click(screen.getByRole('button', { name: SELECT }));

    expect(onLink).toHaveBeenCalledWith('root', ROOT);
  });

  it('drops an answer that lands after the picker closed', async () => {
    renderList();
    open();
    const late = await nextRead(1);
    fireEvent.click(screen.getByRole('button', { name: CANCEL }));
    expect(late.signal.aborted).toBe(true);
    await late.answer([REPORTS]);

    open();

    expect(screen.getByRole('status', { name: LOADING })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reports' })).not.toBeInTheDocument();
    const again = await nextRead(2);
    await again.answer([folder('folder-archive', 'Archive')]);
    expect(screen.getByRole('button', { name: 'Archive' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reports' })).not.toBeInTheDocument();
  });
});

describe('DriveFolderPickerDialog — the retry re-reads the same folder', () => {
  it('keeps the failure and the focus through a second failure, then shows the folder', async () => {
    renderList();
    open();
    await (await nextRead(1)).fail();
    expect(screen.getByText(FAILURE)).toBeInTheDocument();
    const retry = screen.getByRole('button', { name: RETRY });
    retry.focus();

    fireEvent.click(retry);

    const second = await nextRead(2);
    expect(second.folderId).toBe('root');
    expect(retry).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByText(FAILURE)).toBeInTheDocument();
    await second.fail();
    expect(screen.getByText(FAILURE)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: RETRY })).toBe(retry);
    expect(retry).toHaveFocus();
    expect(retry).not.toHaveAttribute('aria-busy');

    fireEvent.click(retry);

    const third = await nextRead(3);
    expect(third.folderId).toBe('root');
    await third.answer([REPORTS]);
    expect(screen.queryByText(FAILURE)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reports' })).toBeInTheDocument();
  });

  it('sends one retry at a time while its answer is awaited', async () => {
    renderList();
    open();
    await (await nextRead(1)).fail();
    const retry = screen.getByRole('button', { name: RETRY });

    fireEvent.click(retry);
    await nextRead(2);
    fireEvent.click(retry);
    await act(async () => {});

    expect(reads).toHaveLength(2);
  });

  it('drops a retry the closing interrupted, and reads afresh at the next opening', async () => {
    renderList();
    open();
    await (await nextRead(1)).fail();
    fireEvent.click(screen.getByRole('button', { name: RETRY }));
    const retry = await nextRead(2);

    fireEvent.click(screen.getByRole('button', { name: CANCEL }));

    expect(retry.signal.aborted).toBe(true);
    await retry.answer([REPORTS]);
    open();
    expect(screen.getByRole('status', { name: LOADING })).toBeInTheDocument();
    expect(screen.queryByText(FAILURE)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reports' })).not.toBeInTheDocument();
    expect((await nextRead(3)).folderId).toBe('root');
  });

  it('drops a retry overtaken by a navigation', async () => {
    renderList();
    open();
    await (await nextRead(1)).answer([REPORTS]);
    fireEvent.click(screen.getByRole('button', { name: 'Reports' }));
    await (await nextRead(2)).fail();
    fireEvent.click(screen.getByRole('button', { name: RETRY }));
    const retry = await nextRead(3);
    expect(retry.folderId).toBe('folder-reports');

    fireEvent.click(screen.getByRole('button', { name: ROOT }));

    expect(retry.signal.aborted).toBe(true);
    const root = await nextRead(4);
    expect(root.folderId).toBe('root');
    await root.answer([folder('folder-archive', 'Archive')]);
    await retry.answer([file('file-3', 'secret.pdf')]);
    expect(screen.getByRole('button', { name: 'Archive' })).toBeInTheDocument();
    expect(screen.queryByText('secret.pdf')).not.toBeInTheDocument();
    expect(screen.queryByText(FAILURE)).not.toBeInTheDocument();
  });
});
