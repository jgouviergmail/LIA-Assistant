/**
 * Importing a meeting from a file (owner request 2026-10-24): a published bound
 * is said before a byte is sent; an accepted file opens the import with what the
 * file and the person said, travels, and the meeting's page opens; an upload
 * that did not complete leaves no meeting behind and says why.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, waitFor } from '@testing-library/react';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const mocks = vi.hoisted(() => ({
  limits: { max_bytes: 1000, chunk_max_bytes: 100, max_duration_minutes: 60 },
  push: vi.fn(),
  startImport: vi.fn(),
  remove: vi.fn(),
  upload: vi.fn(),
}));

vi.mock('@/hooks/useApiQuery', () => ({
  useApiQuery: () => ({ data: mocks.limits, error: null, loading: false }),
}));
vi.mock('@/hooks/useMeetingTemplates', () => ({
  useMeetingTemplates: () => ({ templates: [] }),
}));
vi.mock('@/hooks/useLocalizedRouter', () => ({
  useLocalizedRouter: () => ({ push: mocks.push }),
}));
vi.mock('@/lib/meetings/api', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/meetings/api')>()),
  meetingsApi: { startImport: mocks.startImport, remove: mocks.remove },
}));
vi.mock('@/lib/meetings/import-uploader', () => ({ uploadImportFile: mocks.upload }));
vi.mock('@/lib/meetings/import-file', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/meetings/import-file')>()),
  readAudioDuration: () => Promise.resolve(30),
}));

import { MeetingImportDialog } from '../MeetingImportDialog';

const WRITTEN = Date.UTC(2026, 9, 20, 10, 0, 0);

function chooseFile(size: number, name = 'memo.m4a') {
  const file = new File(['x'.repeat(size)], name, { lastModified: WRITTEN });
  fireEvent.change(screen.getByLabelText('meetings.import.file_label'), {
    target: { files: [file] },
  });
  return file;
}

function render() {
  const onOpenChange = vi.fn();
  renderWithProviders(<MeetingImportDialog lng="en" open onOpenChange={onOpenChange} />);
  return onOpenChange;
}

beforeEach(() => {
  mocks.push.mockReset();
  mocks.startImport.mockReset().mockResolvedValue({
    id: 'm1',
    status: 'uploading',
    started_at: '2026-10-20T09:59:30Z',
    engine: { provider: 'local', model: null, diarized: false },
    limits: mocks.limits,
  });
  mocks.remove.mockReset().mockResolvedValue(undefined);
  mocks.upload.mockReset();
});

describe('MeetingImportDialog', () => {
  it('says a file is over the published size before anything is sent', async () => {
    render();
    chooseFile(1001);

    expect(await screen.findByText('meetings.import.refusal_too_large')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /meetings\.import\.submit/ }));
    expect(mocks.startImport).not.toHaveBeenCalled();
  });

  it('imports an accepted file and opens its meeting once every chunk landed', async () => {
    mocks.upload.mockResolvedValue({ kind: 'complete' });
    const onOpenChange = render();
    chooseFile(500);
    // The length the browser read moves the default date back by it.
    await waitFor(() =>
      expect(screen.getByLabelText('meetings.import.recorded_at_label')).not.toHaveValue('')
    );

    fireEvent.click(screen.getByRole('button', { name: /meetings\.import\.submit/ }));

    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith('/dashboard/meetings/m1'));
    const request = mocks.startImport.mock.calls[0][0];
    expect(request).toMatchObject({
      audio_format: 'import_m4a',
      size_bytes: 500,
      language: 'auto',
      template_ref: null,
    });
    // The file's write minus its length, to the minute the date field holds.
    expect(new Date(request.recorded_at).getTime()).toBe(
      Math.floor((WRITTEN - 30_000) / 60_000) * 60_000
    );
    expect(mocks.upload.mock.calls[0][0]).toMatchObject({ meetingId: 'm1', chunkBytes: 100 });
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(mocks.remove).not.toHaveBeenCalled();
  });

  it('an upload refused leaves no meeting behind and says why', async () => {
    mocks.upload.mockResolvedValue({ kind: 'refused', code: 'import_format_mismatch' });
    render();
    chooseFile(500);

    fireEvent.click(screen.getByRole('button', { name: /meetings\.import\.submit/ }));

    expect(await screen.findByText('meetings.errors.import_format_mismatch')).toBeInTheDocument();
    expect(mocks.remove).toHaveBeenCalledWith('m1');
    expect(mocks.push).not.toHaveBeenCalled();
  });
});
