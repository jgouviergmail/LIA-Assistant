/**
 * useHeartbeatHistory — the notifications actually delivered.
 *
 * The endpoint shipped with the domain and nothing consumed it. What this
 * pins is the pair the UI depends on: a monotone first-load flag (so a refetch
 * never unmounts the list) and an exact total that describes the SET, not the
 * page.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';

const { mockUseApiQuery } = vi.hoisted(() => ({ mockUseApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery: mockUseApiQuery }));

import { HEARTBEAT_HISTORY_PAGE_SIZE, useHeartbeatHistory } from '../useHeartbeatHistory';

function reply(over: Record<string, unknown> = {}) {
  return { data: undefined, loading: false, error: null, refetch: vi.fn(), setData: vi.fn(), ...over };
}

beforeEach(() => vi.clearAllMocks());

describe('useHeartbeatHistory', () => {
  it('requests one page of the documented size', () => {
    mockUseApiQuery.mockReturnValue(reply());

    renderHook(() => useHeartbeatHistory(true));

    expect(mockUseApiQuery).toHaveBeenCalledWith(
      `/heartbeat/history?limit=${HEARTBEAT_HISTORY_PAGE_SIZE}`,
      expect.objectContaining({ enabled: true })
    );
  });

  it('skips the request where the section is not shown', () => {
    mockUseApiQuery.mockReturnValue(reply());

    renderHook(() => useHeartbeatHistory(false));

    expect(mockUseApiQuery).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ enabled: false })
    );
  });

  it('keeps the total of the SET, not of the page', () => {
    mockUseApiQuery.mockReturnValue(
      reply({ data: { notifications: [{ id: 'a' }], total: 137 } })
    );

    const { result } = renderHook(() => useHeartbeatHistory(true));

    expect(result.current.notifications).toHaveLength(1);
    expect(result.current.total).toBe(137);
  });

  it('is a first load only before any payload', () => {
    mockUseApiQuery.mockReturnValue(reply({ loading: true }));
    expect(renderHook(() => useHeartbeatHistory(true)).result.current.firstLoad).toBe(true);

    mockUseApiQuery.mockReturnValue(
      reply({ data: { notifications: [], total: 0 }, loading: true })
    );
    expect(renderHook(() => useHeartbeatHistory(true)).result.current.firstLoad).toBe(false);
  });

  it('reports zero rather than undefined when nothing was delivered', () => {
    mockUseApiQuery.mockReturnValue(reply({ data: { notifications: [], total: 0 } }));

    const { result } = renderHook(() => useHeartbeatHistory(true));

    expect(result.current.total).toBe(0);
  });
});
