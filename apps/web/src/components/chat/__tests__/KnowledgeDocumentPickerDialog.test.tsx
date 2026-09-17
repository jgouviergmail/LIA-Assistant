/**
 * KnowledgeDocumentPickerDialog — the « + » offers the person's own documents.
 *
 * The dialog lists the `ready` documents of EVERY knowledge space of the
 * account, active or not (a paused space is named and badged, never hidden),
 * searches them by name, bounds the selection by the room left in the
 * message, and turns each pick into an attachment through the copy endpoint.
 * A document the API refuses is told by its reason, and the rest still land.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

import type { AttachableDocumentsResponse } from '@/types/rag-spaces';
import { ApiError } from '@/lib/api-client';

const { api, toast } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn() },
  toast: { success: vi.fn(), error: vi.fn() },
}));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: api,
}));

import { KnowledgeDocumentPickerDialog } from '../KnowledgeDocumentPickerDialog';

const LISTING: AttachableDocumentsResponse = {
  items: [
    {
      id: 'doc-1',
      space_id: 'space-a',
      space_name: 'Contracts',
      space_is_active: true,
      original_filename: 'lease 2026.pdf',
      content_type: 'application/pdf',
      file_size: 20480,
      created_at: '2026-09-10T09:00:00Z',
    },
    {
      id: 'doc-2',
      space_id: 'space-b',
      space_name: 'Archive',
      space_is_active: false,
      original_filename: 'old lease 2019.pdf',
      content_type: 'application/pdf',
      file_size: 10240,
      created_at: '2026-08-01T09:00:00Z',
    },
  ],
  total: 2,
  limit: 50,
  offset: 0,
  max_limit: 100,
};

const onAttached = vi.fn(() => ({ ok: true as const }));
const onOpenChange = vi.fn();

function renderDialog(remaining = 5) {
  return render(
    <KnowledgeDocumentPickerDialog
      open
      onOpenChange={onOpenChange}
      remaining={remaining}
      onAttached={onAttached}
    />
  );
}

beforeEach(() => {
  api.get.mockReset();
  api.post.mockReset();
  onAttached.mockClear();
  onOpenChange.mockReset();
  toast.error.mockReset();
  api.get.mockResolvedValue(LISTING);
  // The created row is the truth about the COPY (same bytes as the listing's file).
  api.post.mockImplementation(async (_url: string, body: { document_id: string }) => ({
    id: `att-${body.document_id}`,
    original_filename: 'x',
    mime_type: 'application/pdf',
    file_size: LISTING.items.find(d => d.id === body.document_id)?.file_size ?? 0,
    content_type: 'document',
    created_at: '2026-09-17T09:00:00Z',
  }));
});

describe('KnowledgeDocumentPickerDialog', () => {
  it('lists every document with its space, the paused space badged', async () => {
    renderDialog();
    const rows = await screen.findAllByRole('checkbox');
    expect(rows).toHaveLength(2);
    expect(screen.getByText('lease 2026.pdf')).toBeInTheDocument();
    expect(screen.getByText('Contracts')).toBeInTheDocument();
    const archived = screen.getByText('old lease 2019.pdf').closest('li') as HTMLElement;
    expect(within(archived).getByText('Archive')).toBeInTheDocument();
    expect(within(archived).getByText('chat.knowledge_picker.inactive_badge')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/rag-spaces/documents', {
      params: { q: undefined, limit: 50, offset: 0 },
    });
  });

  it('searches by name through the API', async () => {
    renderDialog();
    await screen.findAllByRole('checkbox');
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'lease' } });
    await waitFor(() =>
      expect(api.get).toHaveBeenLastCalledWith('/rag-spaces/documents', {
        params: { q: 'lease', limit: 50, offset: 0 },
      })
    );
  });

  it('attaches each pick through the copy endpoint and closes', async () => {
    renderDialog();
    const [first, second] = await screen.findAllByRole('checkbox');
    fireEvent.click(first);
    fireEvent.click(second);
    fireEvent.click(screen.getByRole('button', { name: /chat\.knowledge_picker\.attach/ }));
    await waitFor(() => expect(onAttached).toHaveBeenCalledTimes(2));
    expect(api.post).toHaveBeenCalledWith('/attachments/from-knowledge-document', {
      space_id: 'space-a',
      document_id: 'doc-1',
    });
    expect(onAttached).toHaveBeenCalledWith({
      id: 'att-doc-1',
      filename: 'lease 2026.pdf',
      mimeType: 'application/pdf',
      size: 20480,
      contentType: 'document',
    });
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it('bounds the selection by the room left in the message', async () => {
    renderDialog(1);
    const [first, second] = await screen.findAllByRole('checkbox');
    fireEvent.click(first);
    expect(second).toBeDisabled();
    expect(screen.getByText('chat.knowledge_picker.remaining')).toBeInTheDocument();
  });

  it('tells a refused document by its reason and still attaches the others', async () => {
    api.post.mockImplementation(async (_url: string, body: { document_id: string }) => {
      if (body.document_id === 'doc-2') {
        throw new ApiError('conflict', 409, { detail: { code: 'document_not_ready' } });
      }
      return {
        id: 'att-doc-1',
        original_filename: 'x',
        mime_type: 'application/pdf',
        file_size: 1,
        content_type: 'document',
        created_at: '2026-09-17T09:00:00Z',
      };
    });
    renderDialog();
    const [first, second] = await screen.findAllByRole('checkbox');
    fireEvent.click(first);
    fireEvent.click(second);
    fireEvent.click(screen.getByRole('button', { name: /chat\.knowledge_picker\.attach/ }));
    await waitFor(() => expect(onAttached).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('chat.knowledge_picker.not_ready')
    );
  });

  it('says when nothing is indexed yet, and when a search finds nothing', async () => {
    api.get.mockResolvedValue({ ...LISTING, items: [], total: 0 });
    renderDialog();
    expect(await screen.findByText('chat.knowledge_picker.empty')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'zzz' } });
    expect(await screen.findByText('chat.knowledge_picker.empty_search')).toBeInTheDocument();
  });

  it('says when the listing fails', async () => {
    api.get.mockRejectedValue(new Error('boom'));
    renderDialog();
    expect(await screen.findByText('chat.knowledge_picker.error')).toBeInTheDocument();
  });
});

describe('KnowledgeDocumentPickerDialog — a cut page is stated', () => {
  it('says how many documents the page shows out of the exact total', async () => {
    api.get.mockResolvedValue({ ...LISTING, total: 120 });
    renderDialog();
    await waitFor(() => expect(screen.getByText('chat.knowledge_picker.more_hint')).toBeInTheDocument());
  });

  it('says nothing about a cut when the page holds the whole set', async () => {
    api.get.mockResolvedValue(LISTING);
    renderDialog();
    await waitFor(() => expect(screen.getAllByRole('checkbox')).toHaveLength(2));
    expect(screen.queryByText('chat.knowledge_picker.more_hint')).not.toBeInTheDocument();
  });
});
