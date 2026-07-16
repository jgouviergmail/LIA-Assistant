/**
 * useStaleGuard — shared staleness guard for polling hooks (audit F037).
 *
 * The guard is the single tested primitive that useUserStatistics, useAPIHealth
 * and useUsageLimits rely on: only the latest request, while still mounted, may
 * commit state. These tests pin the out-of-order and post-unmount behaviour.
 */
import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';

import { useStaleGuard } from '../useStaleGuard';

describe('useStaleGuard (F037)', () => {
  it('marks the earlier request stale once a newer one begins (out-of-order)', () => {
    const { result } = renderHook(() => useStaleGuard());

    const isStaleA = result.current.begin();
    expect(isStaleA()).toBe(false); // A is the current request

    const isStaleB = result.current.begin();
    expect(isStaleA()).toBe(true); // A was superseded by B
    expect(isStaleB()).toBe(false); // B is now current
  });

  it('is mounted while mounted and stale after unmount', () => {
    const { result, unmount } = renderHook(() => useStaleGuard());

    expect(result.current.isMounted()).toBe(true);
    const isStale = result.current.begin();
    expect(isStale()).toBe(false);

    unmount();

    expect(result.current.isMounted()).toBe(false);
    expect(isStale()).toBe(true); // a late response after unmount is stale
  });

  it('returns a stable object and callbacks across renders', () => {
    const { result, rerender } = renderHook(() => useStaleGuard());
    const first = result.current;

    rerender();

    expect(result.current).toBe(first); // memoized — safe in effect/callback deps
    expect(result.current.begin).toBe(first.begin);
    expect(result.current.isMounted).toBe(first.isMounted);
  });
});
