/**
 * `useAttachableDocuments` — the picker's listing hook.
 *
 * The contract under test is what the composer relies on: a fetch keyed by
 * the needle whose LATE answer is dropped (typing "re" then "rep" must never
 * show the "re" page under the "rep" needle), a failure that reads as an
 * error rather than an empty set, and no request at all while the dialog is
 * closed.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

import { ATTACHABLE_PAGE_SIZE, useAttachableDocuments } from '../useAttachableDocuments';
import type { AttachableDocumentsResponse } from '@/types/rag-spaces';

const mockApi = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('@/lib/api-client', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api-client')>('@/lib/api-client');
  return { ...actual, default: mockApi, apiClient: mockApi };
});

afterEach(() => vi.clearAllMocks());

type Deferred = { resolve: (value: unknown) => void; promise: Promise<unknown> };

function deferred(): Deferred {
  let resolve: (value: unknown) => void = () => undefined;
  const promise = new Promise<unknown>(res => {
    resolve = res;
  });
  return { resolve, promise };
}

const page = (name: string): AttachableDocumentsResponse => ({
  items: [
    {
      id: `${name}-id`,
      space_id: 's',
      space_name: 'S',
      space_is_active: true,
      original_filename: name,
      content_type: 'application/pdf',
      file_size: 12,
      created_at: '2026-01-01T00:00:00Z',
    },
  ],
  total: 1,
  limit: ATTACHABLE_PAGE_SIZE,
  offset: 0,
  max_limit: 500,
});

describe('useAttachableDocuments', () => {
  it('drops the late answer of an earlier needle', async () => {
    const first = deferred();
    const second = deferred();
    mockApi.get.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);

    const { result, rerender } = renderHook(
      ({ needle }: { needle: string }) => useAttachableDocuments(needle, true),
      { initialProps: { needle: 're' } }
    );
    expect(result.current.loading).toBe(true);

    rerender({ needle: 'rep' });
    second.resolve(page('report.pdf'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.items.map(item => item.original_filename)).toEqual(['report.pdf']);

    first.resolve(page('recipe.pdf'));
    await Promise.resolve();
    expect(result.current.items.map(item => item.original_filename)).toEqual(['report.pdf']);
    expect(mockApi.get).toHaveBeenLastCalledWith('/rag-spaces/documents', {
      params: { q: 'rep', limit: ATTACHABLE_PAGE_SIZE, offset: 0 },
    });
  });

  it('reads a failed listing as an error, not as an empty set', async () => {
    mockApi.get.mockRejectedValueOnce(new Error('boom'));
    const { result } = renderHook(() => useAttachableDocuments('', true));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe(true);
    expect(result.current.items).toEqual([]);
  });

  it('asks nothing while disabled, and sends no needle for a blank search', async () => {
    mockApi.get.mockResolvedValue(page('a.pdf'));
    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) => useAttachableDocuments('   ', enabled),
      { initialProps: { enabled: false } }
    );
    expect(mockApi.get).not.toHaveBeenCalled();
    expect(result.current.loading).toBe(false);

    rerender({ enabled: true });
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    expect(mockApi.get).toHaveBeenCalledWith('/rag-spaces/documents', {
      params: { q: undefined, limit: ATTACHABLE_PAGE_SIZE, offset: 0 },
    });
  });
});
