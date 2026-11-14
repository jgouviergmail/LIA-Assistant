/**
 * The lane filter, end to end on the client: what is asked of the server,
 * what the URL carries, and what the folded filter block says.
 *
 * The filter has two halves that WIDEN each other — named categories, and
 * « what is filed under nothing » — and three ways to go wrong quietly: an
 * unset half sent as an empty value, a hand-typed id trusted from the URL, and
 * a summary that names a field instead of what the reader is looking at.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { activeFilterCount, describeFilters, hasFilters } from '@/lib/workboard/active-filters';
import { boardParams, workboardApi } from '@/lib/workboard/api';
import { boardHref, filtersFromParams, writeFilters } from '@/lib/workboard/filters-url';

const client = vi.hoisted(() => ({
  get: vi.fn(async () => ({})),
  post: vi.fn(async () => ({})),
  patch: vi.fn(async () => ({})),
  delete: vi.fn(async () => ({})),
}));
vi.mock('@/lib/api-client', () => ({ apiClient: client, ApiError: class extends Error {} }));

beforeEach(() => vi.clearAllMocks());

const HOME = '11111111-1111-4111-8111-111111111111';
const WORK = '22222222-2222-4222-8222-222222222222';

describe('boardParams — the lane filter', () => {
  it('keeps the categories as a LIST, for the repeated query parameter', () => {
    expect(boardParams({ category: [HOME, WORK] })).toEqual({ category: [HOME, WORK] });
  });

  it('sends `uncategorized` only when it is ON, and an empty list never', () => {
    expect(boardParams({ category: [], uncategorized: false })).toEqual({});
    expect(boardParams({ uncategorized: true })).toEqual({ uncategorized: true });
  });
});

describe('the category endpoints', () => {
  it('reads, creates, renames or moves, and deletes under the board’s own prefix', async () => {
    await workboardApi.categories();
    await workboardApi.createCategory({ name: 'Home' });
    await workboardApi.updateCategory(HOME, { position: 0 });
    await workboardApi.removeCategory(HOME);

    expect(client.get).toHaveBeenCalledWith('/workboard/categories');
    expect(client.post).toHaveBeenCalledWith('/workboard/categories', { name: 'Home' });
    expect(client.patch).toHaveBeenCalledWith(`/workboard/categories/${HOME}`, { position: 0 });
    expect(client.delete).toHaveBeenCalledWith(`/workboard/categories/${HOME}`);
  });

  it('sends a move with its lane in the same write', async () => {
    await workboardApi.move('t1', { status: 'done', position: 0, category_id: HOME });
    expect(client.post).toHaveBeenCalledWith('/workboard/tickets/t1/move', {
      status: 'done',
      position: 0,
      category_id: HOME,
    });
  });
});

describe('the URL — the lane filter', () => {
  it('reads the named categories and the unfiled half', () => {
    const filters = filtersFromParams(
      new URLSearchParams(`category=${HOME}&category=${WORK}&uncategorized=1`)
    );
    expect(filters.category).toEqual([HOME, WORK]);
    expect(filters.uncategorized).toBe(true);
  });

  it('drops an id it cannot have written itself', () => {
    // A hand-typed `?category=home` would reach the API as a malformed UUID
    // and answer 422: the board would show a failure for what is only a URL.
    const filters = filtersFromParams(new URLSearchParams(`category=home&category=${HOME}`));
    expect(filters.category).toEqual([HOME]);
  });

  it('writes nothing for an unset filter and round-trips a set one', () => {
    expect(
      writeFilters(new URLSearchParams(), { assignee: 'all', sort: 'position' }).toString()
    ).toBe('');
    const written = writeFilters(new URLSearchParams('ticket=t1'), {
      category: [HOME],
      uncategorized: true,
    });
    expect(written.get('ticket')).toBe('t1');
    expect(filtersFromParams(written)).toMatchObject({ category: [HOME], uncategorized: true });
  });

  it('forgets a lane the reader cleared', () => {
    const cleared = writeFilters(new URLSearchParams(`category=${HOME}&uncategorized=1`), {});
    expect(cleared.toString()).toBe('');
  });

  it('links into one lane of the board', () => {
    expect(boardHref('fr', { category: [HOME] })).toBe(`/fr/dashboard/workboard?category=${HOME}`);
    expect(boardHref('fr', { uncategorized: true })).toBe(
      '/fr/dashboard/workboard?uncategorized=1'
    );
  });
});

describe('the folded summary — the lane filter', () => {
  const t = (key: string) => key;
  const nameOf = (id: string) => (id === HOME ? 'Home' : undefined);

  it('counts the lane filter ONCE, whatever its two halves hold', () => {
    expect(activeFilterCount({ category: [HOME, WORK], uncategorized: true })).toBe(1);
    expect(activeFilterCount({ uncategorized: true })).toBe(1);
    expect(hasFilters({ category: [HOME] })).toBe(true);
    expect(hasFilters({ category: [], uncategorized: false })).toBe(false);
  });

  it('names the categories by their NAME, and the unfiled half in its own words', () => {
    expect(describeFilters({ category: [HOME], uncategorized: true }, t, nameOf)).toBe(
      'Home, workboard.lanes.unfiled'
    );
  });

  it('never prints an id: a category it cannot name is left out, or named by its field', () => {
    expect(describeFilters({ category: [HOME, WORK] }, t, nameOf)).toBe('Home');
    // Nothing nameable at all — the list has not loaded, or the URL carries a
    // lane that is gone. The summary must still say that SOMETHING narrows the
    // board, or it would read « no filter » beside a badge that counts one.
    expect(describeFilters({ category: [WORK] }, t, nameOf)).toBe('workboard.filters.category');
    expect(describeFilters({ category: [WORK] }, t)).toBe('workboard.filters.category');
  });

  it('reads the lanes after the priority and before « overdue »', () => {
    expect(
      describeFilters({ priority: ['high'], category: [HOME], overdue: true }, t, nameOf)
    ).toBe('workboard.priority.high · Home · workboard.filters.overdue');
  });
});
