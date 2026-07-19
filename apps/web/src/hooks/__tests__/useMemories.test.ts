/**
 * useMemories — the memory store behind the settings panel. As with the other
 * CRUD hooks, component tests mock it out, so its contract lives here: the
 * endpoint each operation targets and the **optimistic updaters**, whose
 * subtlety is that every one of them has to keep the `by_category` histogram
 * consistent with the items it just changed — a counter that drifts is a bug
 * nobody notices until the UI shows "3 preferences" above two rows.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderHook, act } from '@/__tests__/test-utils';
import {
  dataQuery,
  mutateSpy,
  mutationResult,
  queryResult,
  setDataSpy,
  takeUpdater,
} from '@/__tests__/api-mocks';

const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));
const { useApiMutation } = vi.hoisted(() => ({ useApiMutation: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation }));

import { useMemories, getEmotionalEmoji } from '../useMemories';
import type { Memory, MemoryListResponse } from '@/hooks/useMemories';

function memory(over: Partial<Memory> = {}): Memory {
  return {
    id: 'm1',
    content: 'Prefers concise answers',
    category: 'preference',
    emotional_weight: 0.4,
    trigger_topic: 'style',
    usage_nuance: 'when answering',
    importance: 3,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    pinned: false,
    ...over,
  };
}

/** The four mutations, in the order the hook declares them. */
const mutate = {
  create: mutateSpy(),
  remove: mutateSpy(),
  update: mutateSpy(),
  removeAll: mutateSpy(),
};
const ORDER = [mutate.create, mutate.remove, mutate.update, mutate.removeAll];

const setData = setDataSpy<MemoryListResponse>();

function cache(over: Partial<MemoryListResponse> = {}): MemoryListResponse {
  return {
    items: [memory()],
    total: 1,
    by_category: { preference: 1 },
    ...over,
  };
}

/** The memories query is the first `useApiQuery` call; categories the second. */
function setupWith(data: MemoryListResponse | undefined) {
  useApiQuery.mockImplementation((endpoint: string) =>
    endpoint === '/memories'
      ? queryResult<MemoryListResponse>({ data, setData })
      : dataQuery({ categories: [{ category: 'preference', count: 1, label: 'Préférences' }] })
  );
  return renderHook(() => useMemories());
}

const setup = (data: MemoryListResponse = cache()) => setupWith(data);

function applyUpdater(previous: MemoryListResponse | undefined) {
  return takeUpdater<MemoryListResponse>(setData)(previous);
}

/** The options the memories query was last called with. */
function queryOptions(): { params?: Record<string, unknown> } {
  const call = [...useApiQuery.mock.calls].reverse().find(c => c[0] === '/memories');
  return call?.[1] ?? {};
}

beforeEach(() => {
  vi.clearAllMocks();
  let cursor = 0;
  useApiMutation.mockImplementation(() =>
    mutationResult({ mutate: ORDER[cursor++ % ORDER.length] })
  );
  Object.values(mutate).forEach(m => m.mockResolvedValue(undefined));
});

describe('getEmotionalEmoji', () => {
  it.each([
    [-9, '🔴'],
    [-7, '🔴'],
    [-5, '🟠'],
    [-3, '🟠'],
    [0, '⚪'],
    [2.9, '⚪'],
    [3, '🟢'],
    [6.9, '🟢'],
    [7, '💚'],
    [10, '💚'],
  ])('maps a weight of %s to %s', (weight, emoji) => {
    expect(getEmotionalEmoji(weight)).toBe(emoji);
  });
});

describe('useMemories — reading', () => {
  it('reads the collection and the category index', () => {
    const { result } = setup();

    expect(useApiQuery).toHaveBeenCalledWith('/memories', expect.objectContaining({}));
    expect(useApiQuery).toHaveBeenCalledWith('/memories/categories', expect.objectContaining({}));
    expect(result.current.memories).toHaveLength(1);
    expect(result.current.total).toBe(1);
    expect(result.current.byCategory).toEqual({ preference: 1 });
    expect(result.current.categories).toHaveLength(1);
  });

  it('falls back to empty collections on a missing payload', () => {
    const { result } = setupWith(undefined);

    expect(result.current.memories).toEqual([]);
    expect(result.current.total).toBe(0);
    expect(result.current.byCategory).toEqual({});
  });

  it('asks for a single category once one is selected', () => {
    const { result } = setup();
    expect(queryOptions().params).toBeUndefined();

    act(() => result.current.setCategoryFilter('event'));

    expect(queryOptions().params).toEqual({ category: 'event' });
    expect(result.current.categoryFilter).toBe('event');
  });
});

describe('useMemories — creating', () => {
  const draft = { content: 'Likes espresso', category: 'preference' as const };

  it('prepends the new memory and recounts its category', async () => {
    const created = memory({ id: 'm2', content: 'Likes espresso' });
    mutate.create.mockResolvedValue(created);
    const { result } = setup();

    await act(async () => {
      await result.current.createMemory(draft);
    });

    expect(mutate.create).toHaveBeenCalledWith('/memories', draft);
    const next = applyUpdater(cache());
    expect(next?.items.map(m => m.id)).toEqual(['m2', 'm1']);
    expect(next?.total).toBe(2);
    expect(next?.by_category).toEqual({ preference: 2 });
  });

  it('writes nothing when the creation is refused', async () => {
    mutate.create.mockResolvedValue(undefined);
    const { result } = setup();

    await act(async () => {
      await result.current.createMemory(draft);
    });

    expect(setData).not.toHaveBeenCalled();
  });
});

describe('useMemories — deleting', () => {
  it('removes the memory and keeps the histogram consistent', async () => {
    const { result } = setup();

    await act(async () => {
      await result.current.deleteMemory('m1');
    });

    expect(mutate.remove).toHaveBeenCalledWith('/memories/m1');
    const next = applyUpdater(
      cache({
        items: [memory(), memory({ id: 'm2', category: 'event' })],
        total: 2,
        by_category: { preference: 1, event: 1 },
      })
    );
    expect(next?.items.map(m => m.id)).toEqual(['m2']);
    expect(next?.total).toBe(1);
    expect(next?.by_category).toEqual({ event: 1 });
  });

  it('never lets the total go negative when the cache lags behind', async () => {
    const { result } = setup();

    await act(async () => {
      await result.current.deleteMemory('ghost');
    });

    expect(applyUpdater(cache({ items: [], total: 0, by_category: {} }))?.total).toBe(0);
  });
});

describe('useMemories — updating', () => {
  it('merges the patch into the row and stamps it', async () => {
    const { result } = setup();

    await act(async () => {
      await result.current.updateMemory('m1', { content: 'Prefers bullet points' });
    });

    expect(mutate.update).toHaveBeenCalledWith('/memories/m1', {
      content: 'Prefers bullet points',
    });
    const next = applyUpdater(cache());
    expect(next?.items[0]).toMatchObject({ id: 'm1', content: 'Prefers bullet points' });
    expect(next?.items[0].updated_at).not.toBe(memory().updated_at);
  });

  it('moves the row between categories in the histogram', async () => {
    const { result } = setup();

    await act(async () => {
      await result.current.updateMemory('m1', { category: 'event' });
    });

    expect(applyUpdater(cache())?.by_category).toEqual({ event: 1 });
  });
});

describe('useMemories — pinning', () => {
  it('pins through the dedicated route without touching the counts', async () => {
    const { result } = setup();

    await act(async () => {
      await result.current.togglePin('m1', true);
    });

    expect(mutate.update).toHaveBeenCalledWith('/memories/m1/pin', { pinned: true });
    const next = applyUpdater(cache());
    expect(next?.items[0].pinned).toBe(true);
    expect(next?.by_category).toEqual({ preference: 1 });
  });
});

describe('useMemories — wiping everything', () => {
  it('clears the whole store by default', async () => {
    const { result } = setup();

    await act(async () => {
      await result.current.deleteAllMemories();
    });

    expect(mutate.removeAll).toHaveBeenCalledWith('/memories');
    const next = applyUpdater(
      cache({ items: [memory(), memory({ id: 'm2', pinned: true })], total: 2 })
    );
    expect(next).toMatchObject({ items: [], total: 0, by_category: {} });
  });

  it('keeps the pinned memories when asked to', async () => {
    const { result } = setup();

    await act(async () => {
      await result.current.deleteAllMemories(true);
    });

    expect(mutate.removeAll).toHaveBeenCalledWith('/memories?preserve_pinned=true');
    const next = applyUpdater(
      cache({
        items: [memory(), memory({ id: 'm2', pinned: true, category: 'event' })],
        total: 2,
        by_category: { preference: 1, event: 1 },
      })
    );
    expect(next?.items.map(m => m.id)).toEqual(['m2']);
    expect(next?.total).toBe(1);
    expect(next?.by_category).toEqual({ event: 1 });
  });
});

describe('useMemories — updaters on an empty cache', () => {
  it.each([
    [
      'create',
      (h: ReturnType<typeof useMemories>) => h.createMemory({ content: 'c', category: 'event' }),
    ],
    ['delete', (h: ReturnType<typeof useMemories>) => h.deleteMemory('m1')],
    ['update', (h: ReturnType<typeof useMemories>) => h.updateMemory('m1', { content: 'c' })],
    ['pin', (h: ReturnType<typeof useMemories>) => h.togglePin('m1', true)],
    ['wipe', (h: ReturnType<typeof useMemories>) => h.deleteAllMemories()],
  ])('%s leaves an empty cache untouched', async (_label, run) => {
    Object.values(mutate).forEach(m => m.mockResolvedValue(memory()));
    const { result } = setup();

    await act(async () => {
      await run(result.current);
    });

    expect(applyUpdater(undefined)).toBeUndefined();
  });
});
