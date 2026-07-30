/**
 * usePeerConnections — the /peers surface hook (peers program, Lot 2).
 *
 * Behavioral oracle: URLs and payloads sent, refetch-on-success of the
 * affected queries, false-return + error-code capture on ApiError (the
 * components map codes to localized toasts), no cache surgery.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

import { ApiError } from '@/lib/api-client';

const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));
const { useApiMutation } = vi.hoisted(() => ({ useApiMutation: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation }));

import { usePeerConnections } from '../usePeerConnections';

interface QueryStub {
  data: unknown;
  loading: boolean;
  error: null;
  refetch: ReturnType<typeof vi.fn>;
  setData: ReturnType<typeof vi.fn>;
}

function queryStub(data: unknown): QueryStub {
  return { data, loading: false, error: null, refetch: vi.fn(), setData: vi.fn() };
}

const stubs: Record<string, QueryStub> = {};
const mutateByMethod: Record<string, ReturnType<typeof vi.fn>> = {};

beforeEach(() => {
  vi.clearAllMocks();
  stubs['/peers/me'] = queryStub({ discovery_enabled: false });
  stubs['/peers/requests'] = queryStub([]);
  stubs['/peers/connections'] = queryStub([]);
  stubs['/peers/blocks'] = queryStub([]);
  stubs['/peers/access-log'] = queryStub([]);
  useApiQuery.mockImplementation((url: string) => stubs[url]);

  mutateByMethod['POST'] = vi.fn().mockResolvedValue({});
  mutateByMethod['PUT'] = vi.fn().mockResolvedValue({});
  mutateByMethod['DELETE'] = vi.fn().mockResolvedValue({});
  useApiMutation.mockImplementation(({ method }: { method: string }) => ({
    mutate: mutateByMethod[method],
    loading: false,
    error: null,
    reset: vi.fn(),
    data: null,
  }));
});

describe('usePeerConnections', () => {
  it('queries the five /peers endpoints', () => {
    renderHook(() => usePeerConnections());
    const urls = useApiQuery.mock.calls.map(call => call[0]);
    expect(urls).toEqual(
      expect.arrayContaining([
        '/peers/me',
        '/peers/requests',
        '/peers/connections',
        '/peers/blocks',
        '/peers/access-log',
      ])
    );
  });

  it('sendRequest posts the payload and refetches requests on success', async () => {
    const { result } = renderHook(() => usePeerConnections());
    let outcome = { ok: false, errorCode: null as string | null };
    await act(async () => {
      outcome = await result.current.sendRequest('peer-1', 'salut');
    });
    expect(outcome).toEqual({ ok: true, errorCode: null });
    expect(mutateByMethod['POST']).toHaveBeenCalledWith('/peers/requests', {
      peer_id: 'peer-1',
      context_message: 'salut',
    });
    expect(stubs['/peers/requests'].refetch).toHaveBeenCalled();
  });

  it('respond posts accept and refetches requests AND connections', async () => {
    const { result } = renderHook(() => usePeerConnections());
    await act(async () => {
      await result.current.respond('conn-1', true);
    });
    expect(mutateByMethod['POST']).toHaveBeenCalledWith('/peers/requests/conn-1/respond', {
      accept: true,
    });
    expect(stubs['/peers/requests'].refetch).toHaveBeenCalled();
    expect(stubs['/peers/connections'].refetch).toHaveBeenCalled();
  });

  it('setShare puts the domain/level payload', async () => {
    const { result } = renderHook(() => usePeerConnections());
    await act(async () => {
      await result.current.setShare('conn-1', 'calendar', 'availability');
    });
    expect(mutateByMethod['PUT']).toHaveBeenCalledWith('/peers/connections/conn-1/shares', {
      domain: 'calendar',
      level: 'availability',
    });
    expect(stubs['/peers/connections'].refetch).toHaveBeenCalled();
  });

  it('setDiscovery puts the toggle and refetches me', async () => {
    const { result } = renderHook(() => usePeerConnections());
    await act(async () => {
      await result.current.setDiscovery(true);
    });
    expect(mutateByMethod['PUT']).toHaveBeenCalledWith('/peers/me', {
      discovery_enabled: true,
    });
    expect(stubs['/peers/me'].refetch).toHaveBeenCalled();
  });

  it('block posts then refetches blocks, requests and connections (severed state)', async () => {
    const { result } = renderHook(() => usePeerConnections());
    await act(async () => {
      await result.current.block('peer-1');
    });
    expect(mutateByMethod['POST']).toHaveBeenCalledWith('/peers/blocks', { peer_id: 'peer-1' });
    expect(stubs['/peers/blocks'].refetch).toHaveBeenCalled();
    expect(stubs['/peers/requests'].refetch).toHaveBeenCalled();
    expect(stubs['/peers/connections'].refetch).toHaveBeenCalled();
  });

  it('search returns matches without touching the queries', async () => {
    mutateByMethod['POST'].mockResolvedValueOnce([
      { peer_id: 'p1', display_name: 'Peer Beta', email_hint: 'b…@t….local' },
    ]);
    const { result } = renderHook(() => usePeerConnections());
    let searchResult = { matches: null as unknown, errorCode: null as string | null };
    await act(async () => {
      searchResult = await result.current.search('Peer Beta');
    });
    expect(mutateByMethod['POST']).toHaveBeenCalledWith('/peers/discovery/search', {
      full_name: 'Peer Beta',
    });
    expect(searchResult.matches).toHaveLength(1);
    expect(searchResult.errorCode).toBeNull();
  });

  it('carries the backend error code with the failed outcome (ApiError)', async () => {
    mutateByMethod['POST'].mockRejectedValueOnce(
      new ApiError('Bad Request', 400, { detail: 'peers_already_connected' })
    );
    const { result } = renderHook(() => usePeerConnections());
    let outcome = { ok: true, errorCode: null as string | null };
    await act(async () => {
      outcome = await result.current.sendRequest('peer-1');
    });
    expect(outcome).toEqual({ ok: false, errorCode: 'peers_already_connected' });
  });

  it('unknown error shapes yield a null code (generic toast fallback)', async () => {
    mutateByMethod['DELETE'].mockRejectedValueOnce(new Error('network down'));
    const { result } = renderHook(() => usePeerConnections());
    let outcome = { ok: true, errorCode: 'x' as string | null };
    await act(async () => {
      outcome = await result.current.removeConnection('conn-1');
    });
    expect(outcome).toEqual({ ok: false, errorCode: null });
  });
});
