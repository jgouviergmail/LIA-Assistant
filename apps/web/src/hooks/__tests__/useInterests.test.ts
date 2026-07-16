/**
 * Unit tests for `useInterests`.
 *
 * Two layers:
 *  - the pure weight → color/variant helpers (exhaustive threshold coverage);
 *  - the hook's derived state and optimistic-update callbacks, with the
 *    underlying `useApiQuery` (routed by endpoint) and `useApiMutation` mocked.
 *    Optimistic updates are asserted by applying the captured setData updater to
 *    a known previous state.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const mockMutate = vi.fn();
const mockSetData = vi.fn();
const mockUseApiQuery = vi.hoisted(() => vi.fn());
const mockUseApiMutation = vi.hoisted(() => vi.fn());

vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery: mockUseApiQuery }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation: mockUseApiMutation }));

import {
  getWeightBadgeVariant,
  getWeightColorClass,
  useInterests,
  type Interest,
  type InterestListResponse,
} from '../useInterests';

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

describe('getWeightColorClass', () => {
  it('maps weight buckets to color classes', () => {
    expect(getWeightColorClass(0.9)).toBe('text-green-500');
    expect(getWeightColorClass(0.8)).toBe('text-green-500');
    expect(getWeightColorClass(0.6)).toBe('text-emerald-500');
    expect(getWeightColorClass(0.4)).toBe('text-yellow-500');
    expect(getWeightColorClass(0.2)).toBe('text-orange-500');
    expect(getWeightColorClass(0.1)).toBe('text-red-500');
  });
});

describe('getWeightBadgeVariant', () => {
  it('maps weight buckets to badge variants', () => {
    expect(getWeightBadgeVariant(0.7)).toBe('default');
    expect(getWeightBadgeVariant(0.4)).toBe('secondary');
    expect(getWeightBadgeVariant(0.3)).toBe('outline');
  });
});

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

function interest(over: Partial<Interest> = {}): Interest {
  return {
    id: 'i1',
    topic: 'AI',
    category: 'technology',
    weight: 0.5,
    status: 'active',
    positive_signals: 0,
    negative_signals: 0,
    last_mentioned_at: null,
    last_notified_at: null,
    created_at: '2025-01-01T00:00:00Z',
    ...over,
  };
}

const LIST: InterestListResponse = {
  interests: [
    interest({ id: 'i1', category: 'technology', status: 'active' }),
    interest({ id: 'i2', category: 'sports', status: 'blocked' }),
    interest({ id: 'i3', category: 'science', status: 'dormant' }),
  ],
  total: 3,
  active_count: 1,
  blocked_count: 1,
  dormant_count: 1,
};

function routeQuery(list: InterestListResponse = LIST): void {
  mockUseApiQuery.mockImplementation((endpoint: string) => {
    if (endpoint === '/interests') {
      return { data: list, loading: false, error: null, refetch: vi.fn(), setData: mockSetData };
    }
    if (endpoint === '/interests/categories') {
      return { data: { categories: [] }, loading: false, error: null, refetch: vi.fn(), setData: vi.fn() };
    }
    return { data: undefined, loading: false, error: null, refetch: vi.fn(), setData: vi.fn() };
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseApiMutation.mockReturnValue({
    mutate: mockMutate,
    loading: false,
    error: null,
    reset: vi.fn(),
    data: null,
  });
  routeQuery();
});
afterEach(() => vi.clearAllMocks());

describe('useInterests — derived state', () => {
  it('exposes counts and all interests', () => {
    const { result } = renderHook(() => useInterests());
    expect(result.current.total).toBe(3);
    expect(result.current.activeCount).toBe(1);
    expect(result.current.blockedCount).toBe(1);
    expect(result.current.dormantCount).toBe(1);
    expect(result.current.allInterests).toHaveLength(3);
  });

  it('filters client-side by category and status', () => {
    const { result } = renderHook(() => useInterests());

    act(() => result.current.setCategoryFilter('technology'));
    expect(result.current.interests.map((i) => i.id)).toEqual(['i1']);

    act(() => {
      result.current.setCategoryFilter(null);
      result.current.setStatusFilter('blocked');
    });
    expect(result.current.interests.map((i) => i.id)).toEqual(['i2']);
  });
});

describe('useInterests — optimistic updates', () => {
  it('createInterest prepends the created interest and bumps counts', async () => {
    const created = interest({ id: 'i9', topic: 'New' });
    mockMutate.mockResolvedValueOnce(created);

    const { result } = renderHook(() => useInterests());
    await act(async () => {
      await result.current.createInterest({ topic: 'New', category: 'technology' });
    });

    expect(mockMutate).toHaveBeenCalledWith('/interests', {
      topic: 'New',
      category: 'technology',
    });
    const updater = mockSetData.mock.calls.at(-1)![0];
    const next = updater(LIST);
    expect(next.interests[0].id).toBe('i9');
    expect(next.total).toBe(4);
    expect(next.active_count).toBe(2);
  });

  it('deleteInterest removes it and decrements the matching status count', async () => {
    mockMutate.mockResolvedValueOnce(undefined);
    const { result } = renderHook(() => useInterests());
    await act(async () => {
      await result.current.deleteInterest('i2'); // blocked
    });

    expect(mockMutate).toHaveBeenCalledWith('/interests/i2');
    const updater = mockSetData.mock.calls.at(-1)![0];
    const next = updater(LIST);
    expect(next.interests.map((i: Interest) => i.id)).toEqual(['i1', 'i3']);
    expect(next.total).toBe(2);
    expect(next.blocked_count).toBe(0);
  });

  it('submitFeedback(thumbs_up) raises weight and positive signals', async () => {
    mockMutate.mockResolvedValueOnce(undefined);
    const { result } = renderHook(() => useInterests());
    await act(async () => {
      await result.current.submitFeedback('i1', 'thumbs_up');
    });

    expect(mockMutate).toHaveBeenCalledWith('/interests/i1/feedback', { feedback: 'thumbs_up' });
    const updater = mockSetData.mock.calls.at(-1)![0];
    const next = updater(LIST);
    const i1 = next.interests.find((i: Interest) => i.id === 'i1')!;
    expect(i1.positive_signals).toBe(2);
    expect(i1.weight).toBeCloseTo(0.6);
  });

  it('submitFeedback(block) flips status to blocked', async () => {
    mockMutate.mockResolvedValueOnce(undefined);
    const { result } = renderHook(() => useInterests());
    await act(async () => {
      await result.current.submitFeedback('i1', 'block');
    });
    const updater = mockSetData.mock.calls.at(-1)![0];
    const next = updater(LIST);
    const i1 = next.interests.find((i: Interest) => i.id === 'i1')!;
    expect(i1.status).toBe('blocked');
  });
});
