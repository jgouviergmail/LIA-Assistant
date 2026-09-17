/**
 * DriveSourcesList — a sync is preceded by its count.
 *
 * Synchronising a Drive folder now indexes its sub-folders too. The list
 * asks the API what one sync WOULD index (the preflight, computed by the
 * code that indexes) and, past the threshold the API publishes, shows the
 * exact figures and lets the person confirm or cancel. Under the threshold
 * the sync starts at once; a preflight the API cannot compute starts nothing.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import type { RAGDrivePreflight, RAGDriveSource } from '@/types/rag-spaces';

const { preflightFolder, toast } = vi.hoisted(() => ({
  preflightFolder: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
}));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/hooks/useDriveSources', async importOriginal => ({
  ...(await importOriginal<typeof import('@/hooks/useDriveSources')>()),
  useDrivePreflight: () => ({ preflightFolder }),
}));

import { DriveSourcesList } from '../DriveSourcesList';

const SOURCE: RAGDriveSource = {
  id: 'src-1',
  folder_id: 'folder-1',
  folder_name: 'Reports',
  sync_status: 'idle',
  last_sync_at: null,
  file_count: 0,
  synced_file_count: 0,
  error_message: null,
  created_at: '2026-09-17T09:00:00Z',
};

function report(over: Partial<RAGDrivePreflight> = {}): RAGDrivePreflight {
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

const onSync = vi.fn();

function renderList() {
  return render(
    <DriveSourcesList
      spaceId="space-1"
      sources={[SOURCE]}
      onLink={vi.fn()}
      onUnlink={vi.fn()}
      onSync={onSync}
    />
  );
}

beforeEach(() => {
  preflightFolder.mockReset();
  onSync.mockReset();
  toast.error.mockReset();
});

describe('DriveSourcesList — sync preflight', () => {
  it('starts the sync at once under the threshold', async () => {
    preflightFolder.mockResolvedValue(report({ to_index: 3, requires_confirmation: false }));
    renderList();
    fireEvent.click(screen.getByRole('button', { name: 'spaces.drive.sync_now' }));
    await waitFor(() => expect(onSync).toHaveBeenCalledWith('src-1'));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('shows the exact figures past the threshold and syncs only on confirm', async () => {
    preflightFolder.mockResolvedValue(report());
    renderList();
    fireEvent.click(screen.getByRole('button', { name: 'spaces.drive.sync_now' }));
    const dialog = await screen.findByRole('alertdialog');
    expect(onSync).not.toHaveBeenCalled();
    // The count is the subject; the breakdown says where it comes from.
    expect(dialog).toHaveTextContent('spaces.drive.confirm.to_index');
    expect(dialog).toHaveTextContent('spaces.drive.confirm.breakdown');
    expect(dialog).not.toHaveTextContent('spaces.drive.confirm.truncated');
    fireEvent.click(screen.getByRole('button', { name: 'spaces.drive.confirm.confirm' }));
    await waitFor(() => expect(onSync).toHaveBeenCalledWith('src-1'));
  });

  it('cancelling starts nothing', async () => {
    preflightFolder.mockResolvedValue(report());
    renderList();
    fireEvent.click(screen.getByRole('button', { name: 'spaces.drive.sync_now' }));
    await screen.findByRole('alertdialog');
    fireEvent.click(screen.getByRole('button', { name: 'common.cancel' }));
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
    expect(onSync).not.toHaveBeenCalled();
  });

  it('says « at least » when the walk was cut, and names what the space cannot hold', async () => {
    preflightFolder.mockResolvedValue(report({ truncated: true, over_capacity: 3 }));
    renderList();
    fireEvent.click(screen.getByRole('button', { name: 'spaces.drive.sync_now' }));
    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toHaveTextContent('spaces.drive.confirm.truncated');
    expect(dialog).toHaveTextContent('spaces.drive.confirm.over_capacity');
  });

  it('a preflight the API cannot compute starts no sync and says so', async () => {
    preflightFolder.mockRejectedValue(new Error('502'));
    renderList();
    fireEvent.click(screen.getByRole('button', { name: 'spaces.drive.sync_now' }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('spaces.drive.preflight_error'));
    expect(onSync).not.toHaveBeenCalled();
  });
});

describe('DriveSourcesList — one count at a time', () => {
  it('a second click while the count runs walks the Drive no second time', async () => {
    let settle: (value: RAGDrivePreflight) => void = () => undefined;
    preflightFolder.mockImplementation(
      () =>
        new Promise<RAGDrivePreflight>(resolve => {
          settle = resolve;
        })
    );
    renderList();
    const button = screen.getByRole('button', { name: 'spaces.drive.sync_now' });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(preflightFolder).toHaveBeenCalledTimes(1);
    settle(report({ requires_confirmation: false }));
    await waitFor(() => expect(onSync).toHaveBeenCalledTimes(1));
  });
});
