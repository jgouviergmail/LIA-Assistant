/**
 * Keeping a file in a space (lot 5): the person picks the space, the server reads the file. A space
 * another domain manages takes nothing by hand, and a refusal leaves the list open.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { RAGSpace } from '@/types/rag-spaces';

const { get, post, success, refusal } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  success: vi.fn(),
  refusal: vi.fn(),
}));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get, post },
}));
vi.mock('sonner', () => ({ toast: { success } }));
vi.mock('@/lib/workbench/errors', () => ({ workbenchRefusal: refusal }));
vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string>) =>
      values ? `${key} ${JSON.stringify(values)}` : key,
  }),
}));

import { ApiError } from '@/lib/api-client';

import { KeepDialog, type Keeping } from '../KeepDialog';

function space(id: string, name: string, kind: RAGSpace['kind'] = null): RAGSpace {
  return {
    id,
    name,
    description: null,
    is_active: true,
    kind,
    is_favorite: false,
    document_count: 0,
    ready_document_count: 0,
    total_size: 0,
    created_at: '2026-11-01T00:00:00Z',
    updated_at: '2026-11-01T00:00:00Z',
  };
}

const FILE: Keeping = { kind: 'file', name: 'Plan.pdf', file_id: 'f1' };
const ATTACHMENT: Keeping = {
  kind: 'attachment',
  name: 'The invoice',
  filename: 'Invoice.pdf',
  message_id: 'm1',
  attachment_id: 'a1',
};

function dialog(what: Keeping = FILE) {
  const onClose = vi.fn();
  render(<KeepDialog lng="en" what={what} onClose={onClose} />);
  return { user: userEvent.setup(), onClose };
}

beforeEach(() => {
  vi.clearAllMocks();
  refusal.mockReturnValue(null);
  post.mockResolvedValue({ document_id: 'd1' });
  get.mockResolvedValue({
    spaces: [space('s1', 'Work'), space('s2', 'Kept answers', 'bookmarks')],
  });
});

describe('KeepDialog', () => {
  it('offers the person’s own spaces, never one a domain manages', async () => {
    dialog();

    expect(await screen.findByRole('button', { name: 'Work' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Kept answers' })).not.toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('keeps a file by its id alone', async () => {
    const { user, onClose } = dialog();

    await user.click(await screen.findByRole('button', { name: 'Work' }));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(post).toHaveBeenCalledExactlyOnceWith('/tool-assists/spaces/keep-file', {
      space_id: 's1',
      file_id: 'f1',
    });
    expect(success).toHaveBeenCalledWith('workbench.assist.keep.done {"space":"Work"}');
  });

  it('keeps an attachment with its message and its name', async () => {
    const { user } = dialog(ATTACHMENT);

    await user.click(await screen.findByRole('button', { name: 'Work' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/tool-assists/spaces/keep-attachment', {
        space_id: 's1',
        message_id: 'm1',
        attachment_id: 'a1',
        filename: 'Invoice.pdf',
      })
    );
  });

  it('says there is no space to keep it in', async () => {
    get.mockResolvedValue({ spaces: [space('s2', 'Kept answers', 'bookmarks')] });
    dialog();

    expect(await screen.findByText('workbench.assist.keep.none')).toBeInTheDocument();
  });

  it('says the spaces could not be read', async () => {
    get.mockRejectedValue(new Error('down'));
    dialog();

    expect(await screen.findByRole('alert')).toHaveTextContent('workbench.assist.keep.failed');
  });

  it('says why the space refused, and leaves another to pick', async () => {
    post.mockRejectedValueOnce(new Error('refused'));
    refusal.mockReturnValueOnce({ key: 'workbench.errors.too_large', values: { size: '10' } });
    const { user, onClose } = dialog();

    await user.click(await screen.findByRole('button', { name: 'Work' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('workbench.errors.too_large');
    expect(onClose).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Work' }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it.each([
    [400, 'workbench.assist.keep.full'],
    [413, 'workbench.assist.keep.too_large'],
    [415, 'workbench.assist.keep.wrong_type'],
    [500, 'workbench.assist.keep.failed'],
  ])('words a space’s %i', async (status, words) => {
    post.mockRejectedValueOnce(new ApiError('refused', status));
    const { user } = dialog();

    await user.click(await screen.findByRole('button', { name: 'Work' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(words);
  });

  it('keeps once on a double press', async () => {
    let answer = (_value: unknown) => {};
    post.mockReturnValueOnce(new Promise(resolve => (answer = resolve)));
    const { user, onClose } = dialog();

    await user.dblClick(await screen.findByRole('button', { name: 'Work' }));
    answer({ document_id: 'd1' });

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(post).toHaveBeenCalledOnce();
  });
});
