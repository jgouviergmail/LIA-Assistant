import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
const { useAuth, post } = vi.hoisted(() => ({ useAuth: vi.fn(), post: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { post },
}));
vi.mock('@/lib/logger', () => ({ logger: { error: vi.fn() } }));
import { useSmsArchive } from '../useSmsArchive';
import { publishApplicationResources } from '@/lib/application-resources';
import type { SmsPage } from '@/types/sms';
const page: SmsPage = {
  items: [],
  total: 8,
  revision: 1,
  as_of: '2026-10-19T00:00:00Z',
  next_cursor: 'opaque',
};
beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({ user: { id: 'owner' } });
});
it('sends private search terms in a POST body and keeps exact total and opaque cursor', async () => {
  post.mockResolvedValue(page);
  const { result } = renderHook(() => useSmsArchive({ query: 'private medicine', limit: 20 }));
  await waitFor(() => expect(result.current.data?.total).toBe(8));
  expect(post.mock.calls[0][0]).toBe('/sms/search');
  expect(post.mock.calls[0][1]).toEqual({ query: 'private medicine', limit: 20 });
  expect(result.current.data?.next_cursor).toBe('opaque');
});
it('aborts superseded reads and rejects late results from the old filter or account', async () => {
  let finish: ((value: SmsPage) => void) | undefined;
  post
    .mockImplementationOnce(
      () =>
        new Promise<SmsPage>(resolve => {
          finish = resolve;
        })
    )
    .mockResolvedValue(page);
  const { result, rerender } = renderHook(({ query }) => useSmsArchive({ query }), {
    initialProps: { query: 'one' },
  });
  await waitFor(() => expect(post).toHaveBeenCalledOnce());
  const signal: AbortSignal = post.mock.calls[0][2].signal;
  rerender({ query: 'two' });
  await waitFor(() => expect(result.current.data?.total).toBe(8));
  expect(signal.aborted).toBe(true);
  await act(async () => finish?.({ ...page, total: 999 }));
  expect(result.current.data?.total).toBe(8);
  post.mockImplementationOnce(() => new Promise(() => {}));
  useAuth.mockReturnValue({ user: { id: 'other' } });
  rerender({ query: 'two' });
  expect(result.current.data).toBeNull();
  await act(async () => {});
});
it('keeps the page in view while a source change re-reads it, then replaces it', async () => {
  // Owner rule 2026-10-21: a refresh is never a visible reload. Emptied first,
  // the archive unmounted under the reader and dropped the focus a deletion
  // meant to restore; an erased SMS still leaves the view, when the fresh
  // page lands.
  const fresh = Promise.withResolvers<SmsPage>();
  post.mockResolvedValueOnce(page).mockReturnValueOnce(fresh.promise);
  const { result } = renderHook(() => useSmsArchive({}));
  await waitFor(() => expect(result.current.data?.total).toBe(8));
  act(() => publishApplicationResources('owner', new Set(['sms'])));
  expect(result.current.data?.total).toBe(8);
  await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
  expect(result.current.loading).toBe(true);
  await act(async () => fresh.resolve({ ...page, total: 7 }));
  await waitFor(() => expect(result.current.data?.total).toBe(7));
});

it('withdraws the page in view when its reread fails', async () => {
  // A failed reread cannot vouch for what is on screen: an erasure may be the
  // very change it was reading, so the erased SMS must not stay displayed.
  post.mockResolvedValueOnce(page).mockRejectedValueOnce(new Error('offline'));
  const { result } = renderHook(() => useSmsArchive({}));
  await waitFor(() => expect(result.current.data?.total).toBe(8));
  act(() => publishApplicationResources('owner', new Set(['sms'])));
  await waitFor(() => expect(result.current.error).not.toBeNull());
  expect(result.current.data).toBeNull();
});

it('keeps the page a failed page turn was leaving', async () => {
  // Only a re-read after a change withdraws what it was replacing; a page turn
  // that failed changes nothing about the page the reader was on.
  post.mockResolvedValueOnce(page).mockRejectedValueOnce(new Error('offline'));
  const { result, rerender } = renderHook(
    ({ cursor }) => useSmsArchive({ cursor }, true, undefined, true),
    { initialProps: { cursor: undefined as string | undefined } }
  );
  await waitFor(() => expect(result.current.data).toEqual(page));
  rerender({ cursor: 'opaque' });
  await waitFor(() => expect(result.current.error).not.toBeNull());
  expect(result.current.data).toEqual(page);
});

it('retains only a previous page of the same private query when explicitly requested', async () => {
  post.mockResolvedValueOnce(page).mockImplementation(() => new Promise(() => {}));
  const { result, rerender } = renderHook(
    ({ query, cursor }) => useSmsArchive({ query, cursor }, true, undefined, true),
    {
      initialProps: { query: 'one', cursor: undefined as string | undefined },
    }
  );
  await waitFor(() => expect(result.current.data).toEqual(page));
  rerender({ query: 'one', cursor: 'opaque' });
  expect(result.current.data).toEqual(page);
  expect(result.current.loading).toBe(true);
  rerender({ query: 'two', cursor: undefined });
  expect(result.current.data).toBeNull();
  await act(async () => {});
});
