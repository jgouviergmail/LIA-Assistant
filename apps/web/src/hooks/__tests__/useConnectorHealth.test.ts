/**
 * Unit tests for `useConnectorHealth` derived state.
 *
 * `useApiQuery` is mocked to inject a controlled health payload; the hook is
 * driven with the default `isAuthenticated: false` so no polling interval or
 * settings fetch is armed — leaving the pure derivation (critical filtering,
 * dismissal, reconnect-pending flag, refetch) under test. localStorage /
 * sessionStorage are reset between tests.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const mockRefetch = vi.fn();
const mockUseApiQuery = vi.hoisted(() => vi.fn());

vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery: mockUseApiQuery }));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

import { OAUTH_HEALTH_RECONNECT_PENDING_KEY } from '@/lib/constants';
import { useConnectorHealth, type ConnectorHealthResponse } from '../useConnectorHealth';

function healthPayload(over: Partial<ConnectorHealthResponse> = {}): ConnectorHealthResponse {
  return {
    connectors: [
      {
        id: 'c1',
        connector_type: 'google',
        display_name: 'Google',
        health_status: 'error',
        severity: 'critical',
        expires_in_minutes: null,
        authorize_url: 'https://auth/c1',
      },
      {
        id: 'c2',
        connector_type: 'microsoft',
        display_name: 'Microsoft',
        health_status: 'healthy',
        severity: 'info',
        expires_in_minutes: 120,
        authorize_url: 'https://auth/c2',
      },
    ],
    has_issues: true,
    critical_count: 1,
    warning_count: 0,
    checked_at: '2025-01-15T12:00:00Z',
    ...over,
  };
}

function setQuery(data: ConnectorHealthResponse | undefined, loading = false): void {
  mockUseApiQuery.mockReturnValue({
    data,
    loading,
    error: null,
    refetch: mockRefetch,
    setData: vi.fn(),
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  sessionStorage.clear();
});
afterEach(() => vi.clearAllMocks());

describe('useConnectorHealth — derived state', () => {
  it('maps an empty query to a null health with no issues', () => {
    setQuery(undefined);
    const { result } = renderHook(() => useConnectorHealth());
    expect(result.current.health).toBeNull();
    expect(result.current.hasIssues).toBe(false);
    expect(result.current.criticalConnectors).toEqual([]);
  });

  it('surfaces only critical connectors as issues', () => {
    setQuery(healthPayload());
    const { result } = renderHook(() => useConnectorHealth());
    expect(result.current.health).not.toBeNull();
    expect(result.current.hasIssues).toBe(true);
    expect(result.current.criticalConnectors.map((c) => c.id)).toEqual(['c1']);
  });

  it('reflects loading from the underlying query', () => {
    setQuery(undefined, true);
    const { result } = renderHook(() => useConnectorHealth());
    expect(result.current.isLoading).toBe(true);
  });
});

describe('useConnectorHealth — actions', () => {
  it('dismissConnector removes it from the critical list', () => {
    setQuery(healthPayload());
    const { result } = renderHook(() => useConnectorHealth());
    expect(result.current.criticalConnectors).toHaveLength(1);

    act(() => result.current.dismissConnector('c1'));
    expect(result.current.criticalConnectors).toHaveLength(0);
    expect(result.current.hasIssues).toBe(false);
  });

  it('markReconnectPending sets the sessionStorage flag', () => {
    setQuery(healthPayload());
    const { result } = renderHook(() => useConnectorHealth());
    act(() => result.current.markReconnectPending());
    expect(sessionStorage.getItem(OAUTH_HEALTH_RECONNECT_PENDING_KEY)).toBe('true');
  });

  it('refetch delegates to the underlying query refetch', async () => {
    setQuery(healthPayload());
    const { result } = renderHook(() => useConnectorHealth());
    await act(async () => {
      await result.current.refetch();
    });
    expect(mockRefetch).toHaveBeenCalledTimes(1);
  });
});

describe('useConnectorHealth — critical notification', () => {
  it('invokes onCritical for a newly detected critical connector', () => {
    setQuery(healthPayload());
    const onCritical = vi.fn();
    renderHook(() => useConnectorHealth({ onCritical }));
    expect(onCritical).toHaveBeenCalledTimes(1);
    expect(onCritical.mock.calls[0][0].map((c: { id: string }) => c.id)).toEqual(['c1']);
  });

  it('does not invoke onCritical when there are no critical connectors', () => {
    setQuery(healthPayload({ connectors: [] }));
    const onCritical = vi.fn();
    renderHook(() => useConnectorHealth({ onCritical }));
    expect(onCritical).not.toHaveBeenCalled();
  });
});
