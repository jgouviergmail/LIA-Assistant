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
it('invalidates visible data immediately after an owner-bound SMS source change', async () => {
  post.mockResolvedValueOnce(page).mockImplementationOnce(() => new Promise(() => {}));
  const { result } = renderHook(() => useSmsArchive({}));
  await waitFor(() => expect(result.current.data?.total).toBe(8));
  act(() => publishApplicationResources('owner', new Set(['sms'])));
  expect(result.current.data).toBeNull();
  await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
});
