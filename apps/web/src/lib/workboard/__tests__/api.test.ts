/**
 * What the board actually ASKS the server for.
 *
 * `boardParams` decides which filters travel. Two of its rules are not
 * cosmetic: an EMPTY needle must not be sent (server-side it folds into a
 * match-everything `q`, so a cleared search box would silently narrow nothing
 * while looking like a filter), and an unset filter must cost no parameter at
 * all, so the server keeps its own default rather than receiving a `null` it
 * has to interpret.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { boardParams, workboardApi } from '@/lib/workboard/api';

const client = vi.hoisted(() => ({
  get: vi.fn(async () => ({})),
  post: vi.fn(async () => ({})),
  patch: vi.fn(async () => ({})),
  delete: vi.fn(async () => ({})),
}));
vi.mock('@/lib/api-client', () => ({ apiClient: client, ApiError: class extends Error {} }));

beforeEach(() => vi.clearAllMocks());

describe('boardParams', () => {
  it('sends nothing at all for an untouched board', () => {
    expect(boardParams({})).toEqual({});
  });

  it('drops an empty multi-select rather than sending an empty value', () => {
    expect(boardParams({ status: [], priority: [] })).toEqual({});
  });

  it('keeps a list as a LIST, for the repeated query parameter', () => {
    expect(boardParams({ status: ['todo', 'done'] })).toEqual({ status: ['todo', 'done'] });
  });

  it('drops a blank search and trims a real one', () => {
    // `?q=` reaches the folding as an empty needle, which matches everything:
    // a cleared box would look like a filter and narrow nothing.
    expect(boardParams({ q: '   ' })).toEqual({});
    expect(boardParams({ q: '  salle ' })).toEqual({ q: 'salle' });
  });

  it('sends `overdue` only when it is ON', () => {
    // `overdue=false` is the server's own default; sending it would be a
    // parameter that changes nothing and a cache key that differs.
    expect(boardParams({ overdue: false })).toEqual({});
    expect(boardParams({ overdue: true })).toEqual({ overdue: true });
  });

  it('sends a zero page offset and a zero closed-days window', () => {
    // `0` is a VALUE, not an absence: « hide nothing that is closed » and « the
    // first page » both mean zero, and a falsy check would drop them.
    expect(boardParams({ offset: 0, closed_days: 0 })).toEqual({ offset: 0, closed_days: 0 });
  });

  it('carries the sort and the page size', () => {
    expect(boardParams({ sort: 'due', limit: 50 })).toEqual({ sort: 'due', limit: 50 });
  });
});

describe('the endpoints', () => {
  it('spells each path once, and nothing else spells one', async () => {
    await workboardApi.board({ q: 'x' });
    expect(client.get).toHaveBeenCalledWith('/workboard/tickets', { params: { q: 'x' } });

    await workboardApi.needsMe(10, 20);
    expect(client.get).toHaveBeenCalledWith('/workboard/needs-me', {
      params: { limit: 10, offset: 20 },
    });

    await workboardApi.detail('t1');
    expect(client.get).toHaveBeenCalledWith('/workboard/tickets/t1');

    await workboardApi.move('t1', { status: 'done', position: 0 });
    expect(client.post).toHaveBeenCalledWith('/workboard/tickets/t1/move', {
      status: 'done',
      position: 0,
    });

    await workboardApi.runNow('t1');
    expect(client.post).toHaveBeenCalledWith('/workboard/tickets/t1/run-now', {});

    await workboardApi.comment('t1', 'hello');
    expect(client.post).toHaveBeenCalledWith('/workboard/tickets/t1/comments', { body: 'hello' });

    await workboardApi.update('t1', { status: 'done' });
    expect(client.patch).toHaveBeenCalledWith('/workboard/tickets/t1', { status: 'done' });

    await workboardApi.remove('t1');
    expect(client.delete).toHaveBeenCalledWith('/workboard/tickets/t1');
  });
});
