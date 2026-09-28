/** Requests belong to the committed effect and only its newest read may publish. */
import { StrictMode } from 'react';
import { act, render, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { BookmarkStateProvider } from '@/lib/bookmark-state-context';
import { useApiQuery } from '../useApiQuery';

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

function reply(data: unknown): Response {
  return new Response(JSON.stringify(data), { headers: { 'Content-Type': 'application/json' } });
}

function pending() {
  return Promise.withResolvers<Response>();
}

afterEach(() => vi.unstubAllGlobals());

describe('useApiQuery — request lifetime', () => {
  it('sends one wire request across the Strict Mode setup-cleanup-setup probe', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockImplementation(async () => reply('ready'));
    vi.stubGlobal('fetch', fetch);
    const { result } = renderHook(
      () => useApiQuery<string>('/lifetime-proof', { componentName: 'Proof' }),
      { wrapper: StrictMode }
    );

    await waitFor(() => expect(result.current.data).toBe('ready'));
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('never sends a read for an effect cleaned up before it can start', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockImplementation(async () => reply('unused'));
    vi.stubGlobal('fetch', fetch);
    const { unmount } = renderHook(() =>
      useApiQuery<string>('/lifetime-proof', { componentName: 'Proof' })
    );
    unmount();
    await act(async () => {});

    expect(fetch).not.toHaveBeenCalled();
  });

  it('does not publish an obsolete result or clear loading for the next query', async () => {
    const old = pending();
    const fresh = pending();
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockReturnValueOnce(old.promise)
      .mockReturnValueOnce(fresh.promise);
    vi.stubGlobal('fetch', fetch);
    const onSuccess = vi.fn();
    const { result, rerender } = renderHook(
      ({ path }) => useApiQuery<string>(path, { componentName: 'Proof', onSuccess }),
      { initialProps: { path: '/old' } }
    );
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    rerender({ path: '/new' });
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));

    await act(async () => old.resolve(reply('obsolete')));
    expect(result.current.data).toBeUndefined();
    expect(result.current.loading).toBe(true);
    expect(onSuccess).not.toHaveBeenCalled();

    await act(async () => fresh.resolve(reply('current')));
    await waitFor(() => expect(result.current.data).toBe('current'));
    expect(result.current.loading).toBe(false);
  });

  it('a late failure cannot replace a newer success', async () => {
    const old = pending();
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockReturnValueOnce(old.promise)
      .mockImplementationOnce(async () => reply('current'));
    vi.stubGlobal('fetch', fetch);
    const onError = vi.fn();
    const { result, rerender } = renderHook(
      ({ path }) => useApiQuery<string>(path, { componentName: 'Proof', onError }),
      { initialProps: { path: '/old' } }
    );
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    rerender({ path: '/new' });
    await waitFor(() => expect(result.current.data).toBe('current'));
    await act(async () => old.reject(new Error('obsolete failure')));

    expect(result.current.data).toBe('current');
    expect(result.current.error).toBeNull();
    expect(onError).not.toHaveBeenCalled();
  });

  it('a manual refresh supersedes and cancels the read already in flight', async () => {
    const old = pending();
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockReturnValueOnce(old.promise)
      .mockImplementationOnce(async () => reply('refreshed'));
    vi.stubGlobal('fetch', fetch);
    const { result } = renderHook(() =>
      useApiQuery<string>('/lifetime-proof', { componentName: 'Proof' })
    );
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    const originalSignal = fetch.mock.calls[0][1]?.signal;
    await act(async () => result.current.refetch());
    expect(originalSignal?.aborted).toBe(true);
    await act(async () => old.resolve(reply('obsolete')));
    expect(result.current.data).toBe('refreshed');
  });

  it('the bookmark provider also reads once in Strict Mode', async () => {
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockImplementation(async () => reply({ message_ids: {} }));
    vi.stubGlobal('fetch', fetch);
    render(
      <StrictMode>
        <BookmarkStateProvider enabled>
          <span>chat</span>
        </BookmarkStateProvider>
      </StrictMode>
    );
    await act(async () => {});
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('an old mutation callback cannot restart a superseded query', async () => {
    const fresh = pending();
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockImplementationOnce(async () => reply('old'))
      .mockReturnValue(fresh.promise);
    vi.stubGlobal('fetch', fetch);
    const { result, rerender } = renderHook(
      ({ path }) => useApiQuery<string>(path, { componentName: 'Proof' }),
      { initialProps: { path: '/old' } }
    );
    await waitFor(() => expect(result.current.data).toBe('old'));
    const oldRefetch = result.current.refetch;
    rerender({ path: '/new' });
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    const freshSignal = fetch.mock.calls[1][1]?.signal;
    act(() => {
      void oldRefetch();
    });
    await act(async () => {});

    expect(fetch).toHaveBeenCalledTimes(2);
    expect(freshSignal?.aborted).toBe(false);
    await act(async () => fresh.resolve(reply('current')));
    expect(result.current.data).toBe('current');
  });

  it.each(['disabled', 'unmounted'] as const)(
    'a mutation callback retained before %s never sends another request',
    async end => {
      const fetch = vi.fn<typeof globalThis.fetch>().mockImplementation(async () => reply('ready'));
      vi.stubGlobal('fetch', fetch);
      const { result, rerender, unmount } = renderHook(
        ({ enabled }) =>
          useApiQuery<string>('/lifetime-proof', { componentName: 'Proof', enabled }),
        { initialProps: { enabled: true } }
      );
      await waitFor(() => expect(result.current.data).toBe('ready'));
      const oldRefetch = result.current.refetch;
      if (end === 'disabled') rerender({ enabled: false });
      else unmount();
      await act(async () => oldRefetch());

      expect(fetch).toHaveBeenCalledTimes(1);
    }
  );

  it.each(['disabled', 'unmounted'] as const)(
    'ignores an in-flight read that finishes after being %s',
    async end => {
      const read = pending();
      const fetch = vi.fn<typeof globalThis.fetch>().mockReturnValue(read.promise);
      vi.stubGlobal('fetch', fetch);
      const onSuccess = vi.fn();
      const { result, rerender, unmount } = renderHook(
        ({ enabled }) =>
          useApiQuery<string>('/lifetime-proof', { componentName: 'Proof', enabled, onSuccess }),
        { initialProps: { enabled: true } }
      );
      await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
      if (end === 'disabled') rerender({ enabled: false });
      else unmount();
      expect(fetch.mock.calls[0][1]?.signal?.aborted).toBe(true);
      // Deliberately ignore cancellation, as a response already being decoded can.
      await act(async () => read.resolve(reply('obsolete')));
      expect(onSuccess).not.toHaveBeenCalled();
      expect(result.current.data).toBeUndefined();
      if (end === 'disabled') expect(result.current.loading).toBe(false);
    }
  );

  it('updates callbacks without another request and publishes to the latest callback', async () => {
    const read = pending();
    const fetch = vi.fn<typeof globalThis.fetch>().mockReturnValue(read.promise);
    vi.stubGlobal('fetch', fetch);
    const oldCallback = vi.fn();
    const currentCallback = vi.fn();
    const { rerender } = renderHook(
      ({ onSuccess }) =>
        useApiQuery<string>('/lifetime-proof', { componentName: 'Proof', onSuccess }),
      { initialProps: { onSuccess: oldCallback } }
    );
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    rerender({ onSuccess: currentCallback });
    await act(async () => read.resolve(reply('ready')));
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(oldCallback).not.toHaveBeenCalled();
    expect(currentCallback).toHaveBeenCalledWith('ready');
  });

  it('starts a new lifetime when only a dependency changes', async () => {
    const old = pending();
    const fresh = pending();
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockReturnValueOnce(old.promise)
      .mockReturnValueOnce(fresh.promise);
    vi.stubGlobal('fetch', fetch);
    const { result, rerender } = renderHook(
      ({ revision }) =>
        useApiQuery<string>('/lifetime-proof', { componentName: 'Proof', deps: [revision] }),
      { initialProps: { revision: 1 } }
    );
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    rerender({ revision: 2 });
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(fetch.mock.calls[0][1]?.signal?.aborted).toBe(true);
    await act(async () => old.resolve(reply('obsolete')));
    expect(result.current.loading).toBe(true);
    await act(async () => fresh.resolve(reply('current')));
    expect(result.current.data).toBe('current');
  });

  it('recognizes a new caller signal and never publishes the canceled response', async () => {
    const old = pending();
    const fresh = pending();
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockReturnValueOnce(old.promise)
      .mockReturnValueOnce(fresh.promise);
    vi.stubGlobal('fetch', fetch);
    const initialController = new AbortController();
    const nextController = new AbortController();
    const onSuccess = vi.fn();
    const { result, rerender } = renderHook(
      ({ signal }) =>
        useApiQuery<string>('/lifetime-proof', {
          componentName: 'Proof',
          config: { signal },
          onSuccess,
        }),
      { initialProps: { signal: initialController.signal } }
    );
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    rerender({ signal: nextController.signal });
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(fetch.mock.calls[0][1]?.signal?.aborted).toBe(true);
    nextController.abort();
    expect(fetch.mock.calls[1][1]?.signal?.aborted).toBe(true);
    await act(async () => {
      old.resolve(reply('obsolete'));
      fresh.resolve(reply('canceled'));
    });
    expect(result.current.data).toBeUndefined();
    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBe(false);
    expect(onSuccess).not.toHaveBeenCalled();
  });
});
