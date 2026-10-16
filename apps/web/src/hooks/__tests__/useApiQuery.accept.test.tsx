/** External server success is explicit; local setData keeps its existing semantics. */
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useApiQuery } from '../useApiQuery';

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

afterEach(() => vi.unstubAllGlobals());

function reply(data: unknown): Response {
  return Response.json(data);
}

describe('useApiQuery external server success', () => {
  it('clears the recovered error, keeps setData local, and exposes a later read failure', async () => {
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockRejectedValueOnce(new Error('initial offline'))
      .mockRejectedValueOnce(new Error('later offline'));
    vi.stubGlobal('fetch', fetch);
    const { result } = renderHook(() =>
      useApiQuery<string>('/success-proof', { componentName: 'Proof' })
    );
    await waitFor(() => expect(result.current.error?.message).toBe('initial offline'));
    act(() => result.current.setData('local edit'));
    expect(result.current.error?.message).toBe('initial offline');

    act(() => result.current.acceptData('server recovery'));

    expect(result.current.data).toBe('server recovery');
    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBe(false);
    expect(fetch).toHaveBeenCalledTimes(1);
    await act(async () => result.current.refetch());
    expect(result.current.error?.message).toBe('later offline');
  });

  it('cancels an older GET so its late body cannot overwrite the accepted POST result', async () => {
    const old = Promise.withResolvers<Response>();
    const fetch = vi.fn<typeof globalThis.fetch>().mockReturnValue(old.promise);
    vi.stubGlobal('fetch', fetch);
    const onSuccess = vi.fn();
    const { result } = renderHook(() =>
      useApiQuery<string>('/success-proof', { componentName: 'Proof', onSuccess })
    );
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    const signal = fetch.mock.calls[0][1]?.signal;

    act(() => result.current.acceptData('post result'));

    expect(signal?.aborted).toBe(true);
    expect(result.current.loading).toBe(false);
    await act(async () => old.resolve(reply('old get')));
    expect(result.current.data).toBe('post result');
    expect(onSuccess.mock.calls).toEqual([['post result']]);
  });

  it('refuses a callback retained from a different endpoint', async () => {
    const fresh = Promise.withResolvers<Response>();
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValueOnce(reply('old endpoint'))
      .mockReturnValueOnce(fresh.promise);
    vi.stubGlobal('fetch', fetch);
    const { result, rerender } = renderHook(
      ({ endpoint }) => useApiQuery<string>(endpoint, { componentName: 'Proof' }),
      { initialProps: { endpoint: '/old' } }
    );
    await waitFor(() => expect(result.current.data).toBe('old endpoint'));
    const oldAccept = result.current.acceptData;
    rerender({ endpoint: '/new' });
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    act(() => oldAccept('obsolete post'));
    expect(fetch.mock.calls[1][1]?.signal?.aborted).toBe(false);
    expect(result.current.loading).toBe(true);
    await act(async () => fresh.resolve(reply('new endpoint')));
    expect(result.current.data).toBe('new endpoint');
  });

  it.each(['disabled', 'unmounted'] as const)('refuses external success after %s', async end => {
    vi.stubGlobal('fetch', vi.fn<typeof globalThis.fetch>().mockResolvedValue(reply('initial')));
    const onSuccess = vi.fn();
    const { result, rerender, unmount } = renderHook(
      ({ enabled }) =>
        useApiQuery<string>('/success-proof', { componentName: 'Proof', enabled, onSuccess }),
      { initialProps: { enabled: true } }
    );
    await waitFor(() => expect(result.current.data).toBe('initial'));
    const accept = result.current.acceptData;
    onSuccess.mockClear();
    if (end === 'disabled') rerender({ enabled: false });
    else unmount();
    act(() => accept('obsolete post'));
    expect(onSuccess).not.toHaveBeenCalled();
    expect(result.current.data).toBe('initial');
  });
});
