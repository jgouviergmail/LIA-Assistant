/**
 * useEffectsJournal — accumulation rules of the action journal (ADR-263).
 *
 * A journal loads more, it does not paginate. The three rules that make that
 * work, and that a naive implementation gets wrong: an offset-0 payload RESETS
 * (a refetch is a fresh journal, never a duplicated one), a row arriving twice
 * across pages is deduplicated by its ledger id, and `firstLoad` is derived
 * from the ABSENCE of data rather than from `error` — which a refetch resets,
 * and which would make the list unmount under the user.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';

import { EFFECTS_PAGE_SIZE, useEffectsJournal } from '@/hooks/useEffectsJournal';
import type { EffectEntry, EffectPage } from '@/types/effects';

const query = vi.hoisted(() => ({
  calls: [] as string[],
  result: {
    data: undefined as EffectPage | undefined,
    loading: false,
    error: null as Error | null,
    refetch: vi.fn(),
  },
}));

vi.mock('@/hooks/useApiQuery', () => ({
  useApiQuery: (endpoint: string) => {
    query.calls.push(endpoint);
    return query.result;
  },
}));

function entry(id: string): EffectEntry {
  return {
    id,
    label_key: 'effects.labels.generic',
    values: {},
    tool_name: 't',
    mutation_policy: 'reversible',
    status: 'succeeded',
    source: 'user',
    execution_mode: 'pipeline',
    approval_kind: null,
    error_code: null,
    claimed_at: '2026-09-04T10:00:00.000Z',
    closed_at: null,
  };
}

function page(entries: EffectEntry[], offset: number, total: number): EffectPage {
  return { entries, total, limit: EFFECTS_PAGE_SIZE, offset };
}

beforeEach(() => {
  query.calls = [];
  query.result = { data: undefined, loading: false, error: null, refetch: vi.fn() };
});

describe('useEffectsJournal', () => {
  it('reports a first load before any payload', () => {
    const { result } = renderHook(() => useEffectsJournal());

    expect(result.current.firstLoad).toBe(true);
    expect(result.current.entries).toBeUndefined();
  });

  it('asks for the first page with the shared page size', () => {
    renderHook(() => useEffectsJournal());

    expect(query.calls[0]).toBe(`/effects/journal?offset=0&limit=${EFFECTS_PAGE_SIZE}`);
  });

  it('exposes the entries and the EXACT total', () => {
    query.result.data = page([entry('a'), entry('b')], 0, 57);
    const { result } = renderHook(() => useEffectsJournal());

    expect(result.current.entries?.map(e => e.id)).toEqual(['a', 'b']);
    expect(result.current.total).toBe(57);
    expect(result.current.firstLoad).toBe(false);
  });

  it('knows more exists when fewer rows are held than the total', () => {
    query.result.data = page([entry('a')], 0, 3);
    const { result } = renderHook(() => useEffectsJournal());

    expect(result.current.hasMore).toBe(true);
  });

  it('knows nothing more exists once every row is held', () => {
    query.result.data = page([entry('a')], 0, 1);
    const { result } = renderHook(() => useEffectsJournal());

    expect(result.current.hasMore).toBe(false);
  });

  it('accumulates the next page rather than replacing the list', () => {
    query.result.data = page([entry('a')], 0, 2);
    const { result, rerender } = renderHook(() => useEffectsJournal());

    act(() => result.current.loadMore());
    query.result.data = page([entry('b')], EFFECTS_PAGE_SIZE, 2);
    rerender();

    expect(result.current.entries?.map(e => e.id)).toEqual(['a', 'b']);
  });

  it('deduplicates a row that arrives on two pages', () => {
    query.result.data = page([entry('a')], 0, 2);
    const { result, rerender } = renderHook(() => useEffectsJournal());

    act(() => result.current.loadMore());
    query.result.data = page([entry('a'), entry('b')], EFFECTS_PAGE_SIZE, 2);
    rerender();

    expect(result.current.entries?.map(e => e.id)).toEqual(['a', 'b']);
  });

  it('RESETS on an offset-0 payload: a refetch is a fresh journal', () => {
    query.result.data = page([entry('a')], 0, 2);
    const { result, rerender } = renderHook(() => useEffectsJournal());
    act(() => result.current.loadMore());
    query.result.data = page([entry('b')], EFFECTS_PAGE_SIZE, 2);
    rerender();

    query.result.data = page([entry('c')], 0, 1);
    rerender();

    expect(result.current.entries?.map(e => e.id)).toEqual(['c']);
  });

  it('sends the filter to the server', () => {
    renderHook(() => useEffectsJournal('failed'));

    expect(query.calls[0]).toContain('status=failed');
  });

  it('asks for everything when no filter is given', () => {
    renderHook(() => useEffectsJournal());

    expect(query.calls[0]).not.toContain('status=');
  });

  it('STARTS A NEW journal when the filter changes', () => {
    query.result.data = page([entry('a')], 0, 2);
    const { result, rerender } = renderHook(
      ({ status }: { status?: 'failed' }) => useEffectsJournal(status),
      { initialProps: {} as { status?: 'failed' } }
    );
    act(() => result.current.loadMore());
    query.result.data = page([entry('b')], EFFECTS_PAGE_SIZE, 2);
    rerender({});
    expect(result.current.entries?.map(e => e.id)).toEqual(['a', 'b']);

    // Switching filter: the accumulated pages belong to the previous set, and
    // the next payload would land at the offset the reader had reached.
    query.result.data = undefined;
    rerender({ status: 'failed' });

    expect(result.current.entries).toBeUndefined();
    expect(query.calls[query.calls.length - 1]).toContain('offset=0');
  });

  it('does not load more while a request is in flight', () => {
    query.result.data = page([entry('a')], 0, 5);
    query.result.loading = true;
    const { result } = renderHook(() => useEffectsJournal());

    act(() => result.current.loadMore());

    expect(query.calls.every(call => call.includes('offset=0'))).toBe(true);
  });

  it('keeps firstLoad false on an error AFTER a payload arrived', () => {
    query.result.data = page([entry('a')], 0, 1);
    const { result, rerender } = renderHook(() => useEffectsJournal());

    query.result.error = new Error('boom');
    rerender();

    expect(result.current.firstLoad).toBe(false);
    expect(result.current.entries?.length).toBe(1);
  });
});
