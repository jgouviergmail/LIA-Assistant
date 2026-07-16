/**
 * Unit tests for `useDebounce`: the value only updates after the delay elapses
 * with no intervening change, and pending timers are cleared on change/unmount.
 * Runs under fake timers for deterministic timing.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';

import { useDebounce } from '../useDebounce';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('useDebounce', () => {
  it('returns the initial value immediately', () => {
    const { result } = renderHook(() => useDebounce('a', 300));
    expect(result.current).toBe('a');
  });

  it('updates only after the delay has fully elapsed', () => {
    const { result, rerender } = renderHook(({ v }) => useDebounce(v, 300), {
      initialProps: { v: 'a' },
    });

    rerender({ v: 'b' });
    expect(result.current).toBe('a'); // not yet

    act(() => vi.advanceTimersByTime(299));
    expect(result.current).toBe('a'); // one ms short

    act(() => vi.advanceTimersByTime(1));
    expect(result.current).toBe('b');
  });

  it('resets the timer when the value changes before the delay (only last wins)', () => {
    const { result, rerender } = renderHook(({ v }) => useDebounce(v, 300), {
      initialProps: { v: 'a' },
    });

    rerender({ v: 'b' });
    act(() => vi.advanceTimersByTime(200));
    rerender({ v: 'c' }); // resets the 300ms window
    act(() => vi.advanceTimersByTime(200));
    expect(result.current).toBe('a'); // neither b nor c committed yet

    act(() => vi.advanceTimersByTime(100));
    expect(result.current).toBe('c'); // only the latest value lands
  });

  it('clears the pending timer on unmount (no late update)', () => {
    const { result, rerender, unmount } = renderHook(({ v }) => useDebounce(v, 300), {
      initialProps: { v: 'a' },
    });
    rerender({ v: 'b' });
    unmount();
    // Advancing after unmount must not throw or update the captured value.
    act(() => vi.advanceTimersByTime(300));
    expect(result.current).toBe('a');
  });
});
