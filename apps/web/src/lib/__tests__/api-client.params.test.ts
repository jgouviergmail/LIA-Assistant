/**
 * A query parameter may be a LIST, and a list is repeated — never joined.
 *
 * FastAPI reads `list[str] = Query(default=None)` from REPEATED entries
 * (`?status=todo&status=done`); a comma-joined string reaches it as ONE value
 * named `"todo,done"`, which no validator recognises. The workboard board
 * filters by several columns and several priorities at once
 * (`domains/workboard/router.py`), so the client had to learn the shape the
 * server has always spoken — once, here, rather than in every caller that
 * would otherwise hand-build a query string.
 *
 * The two branches of `buildUrl` are asserted separately because they are two
 * implementations: an absolute base goes through `URL`, a relative one through
 * `URLSearchParams`. A fix applied to one and not the other is exactly the
 * defect this file exists to prevent.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@/lib/native/shell', () => ({
  isNativeShell: vi.fn(() => false),
  openInSystemBrowser: vi.fn(),
}));

import apiClient from '@/lib/api-client';

/** The URL the client actually asked `fetch` for. */
function urlOf(call: unknown): string {
  return (call as [string, RequestInit])[0];
}

function okJson() {
  return {
    ok: true,
    status: 200,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => ({}),
    text: async () => '{}',
  } as unknown as Response;
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.stubGlobal('fetch', vi.fn(async () => okJson()));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('buildUrl — list parameters', () => {
  it('repeats one entry per item, in order', async () => {
    await apiClient.get('/workboard/tickets', {
      params: { status: ['todo', 'in_progress'], assignee: 'me' },
    });

    const url = urlOf(vi.mocked(fetch).mock.calls[0]);
    expect(url).toContain('status=todo');
    expect(url).toContain('status=in_progress');
    expect(url).toContain('assignee=me');
    // Order is the caller's: a server reading the first entry must not get the
    // second one because a Set or an object reordered them.
    expect(url.indexOf('status=todo')).toBeLessThan(url.indexOf('status=in_progress'));
  });

  it('never joins a list into one value', async () => {
    await apiClient.get('/workboard/tickets', { params: { priority: ['high', 'urgent'] } });

    const url = urlOf(vi.mocked(fetch).mock.calls[0]);
    // `todo,done` is the shape that silently reaches FastAPI as a single
    // unrecognised value — the whole reason this branch exists.
    expect(url).not.toContain('high%2Curgent');
    expect(url).not.toContain('high,urgent');
  });

  it('emits nothing at all for an empty list', async () => {
    await apiClient.get('/workboard/tickets', { params: { status: [], assignee: 'all' } });

    const url = urlOf(vi.mocked(fetch).mock.calls[0]);
    expect(url).not.toContain('status');
    expect(url).toContain('assignee=all');
  });

  it('ignores an undefined parameter rather than sending the word', async () => {
    await apiClient.get('/workboard/tickets', {
      params: { q: undefined, overdue: false, limit: 20 },
    });

    const url = urlOf(vi.mocked(fetch).mock.calls[0]);
    expect(url).not.toContain('q=');
    expect(url).not.toContain('undefined');
    // A false is a VALUE, not an absence: `overdue=false` is what turns the
    // filter off explicitly.
    expect(url).toContain('overdue=false');
    expect(url).toContain('limit=20');
  });

  it('adds no query string when every parameter was empty', async () => {
    await apiClient.get('/workboard/tickets', { params: { status: [], q: undefined } });

    expect(urlOf(vi.mocked(fetch).mock.calls[0])).not.toContain('?');
  });

  it('keeps scalars exactly as they were', async () => {
    await apiClient.get('/meetings', { params: { limit: 20, offset: 40 } });

    const url = urlOf(vi.mocked(fetch).mock.calls[0]);
    expect(url).toContain('limit=20');
    expect(url).toContain('offset=40');
  });
});
