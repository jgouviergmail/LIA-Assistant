/**
 * The categories hook: what it reads, what it derives, what a write answers.
 *
 * Three properties, each a way the manager dialog or a list would otherwise
 * mislead:
 *
 * - the reader's OWN categories are told apart from the ones that are merely
 *   on their board — only their own can receive one of their tickets;
 * - a write answers `{ok, errorCode}` with the backend's stable code, never an
 *   exception the caller may forget to catch, and re-reads the list only when
 *   it succeeded;
 * - a refresh is not a first load: the list on screen stays while it re-reads.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

import { useWorkboardCategories } from '@/hooks/useWorkboardCategories';
import { ApiError } from '@/lib/api-client';
import type { CategoryList, CategoryRow } from '@/types/workboard';

const client = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));
// The read goes through `useApiQuery`, which imports the client's DEFAULT
// export; the writes go through `workboardApi`, which imports the named one.
// Both are the one transport, so both are replaced by the same double.
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  apiClient: client,
  default: client,
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'me' } }) }));

function category(over: Partial<CategoryRow> & { id: string }): CategoryRow {
  return { owner_user_id: 'me', name: over.id, position: 0, ticket_count: 0, ...over };
}

function listing(categories: CategoryRow[]): CategoryList {
  return { categories, max_categories: 20, name_max_chars: 40 };
}

beforeEach(() => {
  vi.clearAllMocks();
  client.get.mockResolvedValue(
    listing([
      category({ id: 'home', position: 0, ticket_count: 3 }),
      category({ id: 'work', position: 1 }),
      category({ id: 'shared', owner_user_id: 'peer' }),
    ])
  );
});

async function mounted() {
  const hook = renderHook(() => useWorkboardCategories(true));
  await waitFor(() => expect(hook.result.current.firstLoad).toBe(false));
  return hook;
}

describe('useWorkboardCategories — reading', () => {
  it('hands out the reader’s OWN categories, never one merely on their board', async () => {
    // The list also carries the category of a ticket held for somebody else:
    // it is on the reader's board, and not theirs to manage.
    const { result } = await mounted();

    expect(result.current.own.map(row => row.id)).toEqual(['home', 'work']);
  });

  it('publishes the caps the instance enforces', async () => {
    const { result } = await mounted();

    expect(result.current.maxCategories).toBe(20);
    expect(result.current.nameMaxChars).toBe(40);
  });

  it('is empty, not broken, before the first answer', () => {
    client.get.mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useWorkboardCategories(true));

    expect(result.current.firstLoad).toBe(true);
    expect(result.current.own).toEqual([]);
  });

  it('asks for nothing while it is switched off', () => {
    renderHook(() => useWorkboardCategories(false));

    expect(client.get).not.toHaveBeenCalled();
  });
});

describe('useWorkboardCategories — writing', () => {
  it('creates, then re-reads the list', async () => {
    const { result } = await mounted();
    client.post.mockResolvedValue(category({ id: 'new' }));

    let outcome;
    await act(async () => {
      outcome = await result.current.create({ name: 'Garden' });
    });

    expect(outcome).toEqual({ ok: true, errorCode: null });
    expect(client.post).toHaveBeenCalledWith('/workboard/categories', { name: 'Garden' });
    expect(client.get).toHaveBeenCalledTimes(2);
  });

  it('answers a refusal with its code and leaves the list alone', async () => {
    const { result } = await mounted();
    client.post.mockRejectedValue(
      new ApiError('refused', 400, { detail: 'workboard_category_name_taken' })
    );

    let outcome;
    await act(async () => {
      outcome = await result.current.create({ name: 'home' });
    });

    expect(outcome).toEqual({ ok: false, errorCode: 'workboard_category_name_taken' });
    expect(client.get).toHaveBeenCalledTimes(1);
  });

  it('renames or moves through one verb', async () => {
    const { result } = await mounted();
    client.patch.mockResolvedValue(category({ id: 'home' }));

    await act(async () => {
      await result.current.update('home', { position: 1 });
    });

    expect(client.patch).toHaveBeenCalledWith('/workboard/categories/home', { position: 1 });
  });

  it('says how many tickets a deletion sent back to the unfiled lane', async () => {
    const { result } = await mounted();
    client.delete.mockResolvedValue({ released: 3 });

    let outcome;
    await act(async () => {
      outcome = await result.current.remove('home');
    });

    expect(outcome).toEqual({ ok: true, errorCode: null, released: 3 });
  });

  it('keeps the list on screen while it re-reads', async () => {
    const { result } = await mounted();
    client.post.mockResolvedValue(category({ id: 'new' }));
    let release: (value: CategoryList) => void = () => {};
    client.get.mockReturnValue(
      new Promise<CategoryList>(resolve => {
        release = resolve;
      })
    );

    let pending: Promise<unknown> = Promise.resolve();
    act(() => {
      pending = result.current.create({ name: 'Garden' });
    });
    await waitFor(() => expect(client.get).toHaveBeenCalledTimes(2));

    expect(result.current.firstLoad).toBe(false);
    expect(result.current.own).toHaveLength(2);

    await act(async () => {
      release(listing([category({ id: 'home' })]));
      await pending;
    });
    expect(result.current.own).toHaveLength(1);
  });
});
