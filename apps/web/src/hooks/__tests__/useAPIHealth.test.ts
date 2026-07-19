/**
 * Unit tests for `useAPIHealth` (audit F010, risk-first).
 *
 * Drives the backend health probe with a stubbed global `fetch`, mocked
 * logging, and the real `useStaleGuard`. Covers the no-user short circuit, the
 * healthy vs structurally-unhealthy (graph not compiled) paths, an HTTP error,
 * a thrown network error, the returned value contract, the isChecking
 * transition, and a re-check when the user identity changes.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

// withContext must be a STABLE reference — the real useLoggingContext memoizes
// it (useMemo), so checkHealth's identity is stable and its effect does not
// re-fire on every render. A fresh function here would loop the health check.
const { stableWithContext } = vi.hoisted(() => ({
  stableWithContext: (o: Record<string, unknown>) => o,
}));

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));
vi.mock('@/lib/logging-context', () => ({
  useLoggingContext: () => ({ withContext: stableWithContext }),
}));

import { useAPIHealth } from '../useAPIHealth';
import { logger } from '@/lib/logger';

const USER = { id: 'u1' };

function stubFetch(impl: () => Promise<unknown>) {
  const fetchMock = vi.fn().mockImplementation(impl);
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function okResponse(body: unknown) {
  return { ok: true, json: () => Promise.resolve(body) };
}

beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe('useAPIHealth', () => {
  it('short-circuits to unavailable when there is no user (no request)', async () => {
    const fetchMock = stubFetch(() => Promise.resolve(okResponse({})));
    const onStatusChange = vi.fn();

    const { result } = renderHook(() => useAPIHealth({ user: null, onStatusChange }));

    await waitFor(() => expect(onStatusChange).toHaveBeenCalledWith(false));
    expect(result.current.apiAvailable).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('reports available when the graph is compiled and healthy', async () => {
    stubFetch(() => Promise.resolve(okResponse({ status: 'healthy', graph_compiled: true })));
    const onStatusChange = vi.fn();

    const { result } = renderHook(() => useAPIHealth({ user: USER, onStatusChange }));

    await waitFor(() => expect(result.current.apiAvailable).toBe(true));
    expect(onStatusChange).toHaveBeenLastCalledWith(true);
    expect(logger.info).toHaveBeenCalled();
  });

  it('reports unavailable when the graph is not compiled', async () => {
    stubFetch(() => Promise.resolve(okResponse({ status: 'healthy', graph_compiled: false })));
    const { result } = renderHook(() => useAPIHealth({ user: USER }));
    await waitFor(() => expect(result.current.isChecking).toBe(false));
    expect(result.current.apiAvailable).toBe(false);
  });

  it('reports unavailable and warns on an HTTP error response', async () => {
    stubFetch(() => Promise.resolve({ ok: false, status: 503, statusText: 'Unavailable' }));
    const { result } = renderHook(() => useAPIHealth({ user: USER }));
    await waitFor(() => expect(result.current.isChecking).toBe(false));
    expect(result.current.apiAvailable).toBe(false);
    expect(logger.warn).toHaveBeenCalled();
  });

  it('reports unavailable and logs on a thrown network error', async () => {
    stubFetch(() => Promise.reject(new TypeError('Failed to fetch')));
    const { result } = renderHook(() => useAPIHealth({ user: USER }));
    await waitFor(() => expect(result.current.isChecking).toBe(false));
    expect(result.current.apiAvailable).toBe(false);
    expect(logger.error).toHaveBeenCalled();
  });

  it('checkHealth resolves to the boolean health status', async () => {
    stubFetch(() => Promise.resolve(okResponse({ status: 'healthy', graph_compiled: true })));
    const { result } = renderHook(() => useAPIHealth({ user: USER }));
    await waitFor(() => expect(result.current.apiAvailable).toBe(true));

    let value: boolean | undefined;
    await act(async () => {
      value = await result.current.checkHealth();
    });
    expect(value).toBe(true);
  });

  it('re-checks when the user identity changes', async () => {
    const fetchMock = stubFetch(() =>
      Promise.resolve(okResponse({ status: 'healthy', graph_compiled: true }))
    );
    const { rerender } = renderHook(
      (props: { user: { id: string } | null }) => useAPIHealth(props),
      {
        initialProps: { user: USER },
      }
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    rerender({ user: { id: 'u2' } });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });
});
