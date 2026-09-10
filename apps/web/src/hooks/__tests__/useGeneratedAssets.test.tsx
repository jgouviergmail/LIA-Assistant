/**
 * One gallery page, and the page a person is left on (ADR-279).
 *
 * Two things the hook owes the section, both about not stranding a reader:
 *
 * - a narrowing resets to the FIRST page, or changing a filter lands on page 4
 *   of a set that now has one;
 * - deleting the last file of the last page must not leave a blank grid under
 *   a pager saying « page 3 of 2 ». The data shrank; the page has to follow it.
 */

import { renderHook, waitFor } from '@testing-library/react';
import { act } from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const query = vi.hoisted(() => ({
  data: null as unknown,
  loading: false,
  error: null as Error | null,
  paths: [] as string[],
  refetch: vi.fn(),
}));

vi.mock('@/hooks/useApiQuery', () => ({
  useApiQuery: (path: string) => {
    query.paths.push(path);
    return { ...query };
  },
}));

import { GALLERY_PAGE_SIZE, galleryPath, useGeneratedAssets } from '@/hooks/useGeneratedAssets';
import type { GeneratedAssetFilters } from '@/types/generated-assets';

function payload(total: number, items = 1) {
  return {
    items: Array.from({ length: items }, (_, index) => ({
      id: `a1b2c3d4-0000-4000-8000-00000000000${index}`,
      title: null,
      original_filename: `f${index}.png`,
      mime_type: 'image/png',
      file_size: 10,
      origin: 'generated_image',
      conversation_id: null,
      created_at: '2026-09-10T08:00:00Z',
      expires_at: '2026-09-11T08:00:00Z',
    })),
    total,
    total_bytes: total * 10,
    limit: GALLERY_PAGE_SIZE,
    offset: 0,
    max_limit: 100,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  query.data = null;
  query.error = null;
  query.paths = [];
});

describe('galleryPath', () => {
  it('costs no parameter for an unset filter', () => {
    const path = galleryPath('images', {}, 0);

    expect(path).toBe(`/generated-assets?family=images&limit=${GALLERY_PAGE_SIZE}`);
  });

  it('never sends a blank search', () => {
    // A blank `q=` narrows nothing while looking like a search.
    expect(galleryPath('images', { q: '   ' }, 0)).not.toContain('q=');
  });

  it('encodes the needle rather than pasting it', () => {
    const path = galleryPath('documents', { q: 'a&b=c' }, 0);

    expect(path).toContain('q=a%26b%3Dc');
    expect(path).not.toContain('q=a&b=c');
  });

  it('omits the default ordering', () => {
    expect(galleryPath('images', { sort: 'created_desc' }, 0)).not.toContain('sort=');
    expect(galleryPath('images', { sort: 'name_asc' }, 0)).toContain('sort=name_asc');
  });
});

describe('the page follows the data', () => {
  it('reports the exact total and the bytes behind it', () => {
    query.data = payload(137);

    const { result } = renderHook(() => useGeneratedAssets('images', {}, true));

    expect(result.current.total).toBe(137);
    expect(result.current.totalBytes).toBe(1370);
  });

  it('goes back to the first page when the filters change', async () => {
    query.data = payload(200, 24);
    const { result, rerender } = renderHook(
      ({ filters }: { filters: GeneratedAssetFilters }) =>
        useGeneratedAssets('images', filters, true),
      { initialProps: { filters: {} as GeneratedAssetFilters } }
    );

    act(() => result.current.setPage(4));
    await waitFor(() => expect(result.current.page).toBe(4));

    rerender({ filters: { q: 'bilan' } });

    expect(result.current.page).toBe(1);
  });

  it('never strands a reader on a page the set no longer has', async () => {
    // Deleting the last file of the last page left a blank grid under a pager
    // reading « page 3 of 2 »: the data shrank and the page stayed.
    query.data = payload(60, 24);
    const { result, rerender } = renderHook(() => useGeneratedAssets('images', {}, true));

    act(() => result.current.setPage(3));
    await waitFor(() => expect(result.current.page).toBe(3));

    query.data = payload(24, 24);
    rerender();

    expect(result.current.totalPages).toBe(1);
    expect(result.current.page).toBe(1);
  });

  it('leaves the page alone while the set still holds it', async () => {
    query.data = payload(60, 24);
    const { result, rerender } = renderHook(() => useGeneratedAssets('images', {}, true));

    act(() => result.current.setPage(2));
    await waitFor(() => expect(result.current.page).toBe(2));

    query.data = payload(59, 24);
    rerender();

    expect(result.current.page).toBe(2);
  });

  it('shows one page for an empty gallery rather than zero', () => {
    query.data = payload(0, 0);

    const { result } = renderHook(() => useGeneratedAssets('images', {}, true));

    expect(result.current.totalPages).toBe(1);
    expect(result.current.page).toBe(1);
  });

  it('is in first load only before the first payload', () => {
    query.data = null;
    const { result, rerender } = renderHook(() => useGeneratedAssets('images', {}, true));
    expect(result.current.firstLoad).toBe(true);

    query.data = payload(1);
    rerender();

    expect(result.current.firstLoad).toBe(false);
  });
});
