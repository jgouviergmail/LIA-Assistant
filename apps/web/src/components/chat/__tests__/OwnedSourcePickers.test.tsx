/**
 * The « + »'s copies of what LIA already gave (owner request 2026-10-24).
 *
 * A kept answer is named by the request that produced it and copied through
 * its own endpoint; a generated file is listed one family at a time, the
 * family travelling to the gallery's own listing.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const { api } = vi.hoisted(() => ({ api: { get: vi.fn(), post: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: api,
}));

import type { Bookmark } from '@/types/bookmarks';
import { BookmarkPickerDialog, bookmarkLabel } from '../BookmarkPickerDialog';
import { GeneratedFilePickerDialog } from '../GeneratedFilePickerDialog';

const BOOKMARK_ID = '11111111-2222-4333-8444-555555555555';
const ASSET_ID = '66666666-7777-4888-8999-000000000000';
const onAttached = vi.fn(() => ({ ok: true as const }));
const created = {
  id: 'att-1',
  original_filename: 'copy',
  mime_type: 'text/markdown',
  file_size: 10,
  content_type: 'document',
};

beforeEach(() => {
  api.get.mockReset();
  api.post.mockReset();
  onAttached.mockClear();
  api.post.mockResolvedValue(created);
});

describe('BookmarkPickerDialog', () => {
  it('names a kept answer by its request, and copies it through its endpoint', async () => {
    api.get.mockResolvedValue({
      items: [
        {
          id: BOOKMARK_ID,
          content: '<p>The <b>agenda</b> for Monday.</p>',
          request_content: 'What is on   Monday?',
          answered_at: '2026-10-20T09:30:00Z',
        },
      ],
      total: 1,
    });
    render(
      <BookmarkPickerDialog open onOpenChange={vi.fn()} remaining={3} onAttached={onAttached} />
    );
    expect(await screen.findByText('What is on Monday?')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/bookmarks', {
      params: { q: undefined, limit: 50, offset: 0 },
    });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: /chat\.attach_picker\.attach/ }));
    await waitFor(() => expect(onAttached).toHaveBeenCalledTimes(1));
    expect(api.post).toHaveBeenCalledWith('/attachments/from-bookmark', {
      bookmark_id: BOOKMARK_ID,
    });
  });

  it('falls back on the answer, markup removed, when no request produced it', () => {
    const bookmark: Bookmark = {
      id: BOOKMARK_ID,
      message_id: null,
      conversation_id: null,
      content: '<p>The <b>agenda</b></p>',
      request_content: null,
      answered_at: '2026-10-20T09:30:00Z',
      created_at: '2026-10-20T09:31:00Z',
      index_state: null,
      indexed_at: null,
      index_usage: null,
      answer_usage: null,
    };
    expect(bookmarkLabel(bookmark)).toBe('The agenda');
  });
});

describe('GeneratedFilePickerDialog', () => {
  it('lists one family at a time and copies the pick', async () => {
    api.get.mockResolvedValue({
      items: [
        {
          id: ASSET_ID,
          title: 'Sunset over the bay',
          original_filename: 'generated_1.png',
          mime_type: 'image/png',
          file_size: 2048,
        },
      ],
      total: 1,
    });
    render(
      <GeneratedFilePickerDialog
        open
        onOpenChange={vi.fn()}
        remaining={3}
        onAttached={onAttached}
      />
    );
    expect(await screen.findByText('Sunset over the bay')).toBeInTheDocument();
    expect(api.get).toHaveBeenLastCalledWith('/generated-assets', {
      params: { family: 'images', q: undefined, limit: 50, offset: 0 },
    });

    fireEvent.click(screen.getByRole('radio', { name: 'chat.generated_picker.family_documents' }));
    await waitFor(() =>
      expect(api.get).toHaveBeenLastCalledWith('/generated-assets', {
        params: { family: 'documents', q: undefined, limit: 50, offset: 0 },
      })
    );

    fireEvent.click(await screen.findByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: /chat\.attach_picker\.attach/ }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/attachments/from-generated', {
        attachment_id: ASSET_ID,
      })
    );
  });
});
