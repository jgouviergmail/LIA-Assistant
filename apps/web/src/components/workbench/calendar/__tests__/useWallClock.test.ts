/**
 * The wall clock of the now line (ADR-369, lot 2): it turns with the minute, on
 * the account's wall, and its timer ends with the screen.
 */
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useWallClock } from '../useWallClock';

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-11-04T09:30:40Z'));
});

afterEach(() => vi.useRealTimers());

describe('useWallClock', () => {
  it('reads the account’s wall', () => {
    const { result } = renderHook(() => useWallClock('Europe/Paris'));

    expect(result.current).toEqual({ date: '2026-11-04', time: '10:30' });
  });

  it('turns when the minute turns, then every minute', () => {
    const { result } = renderHook(() => useWallClock('Europe/Paris'));

    act(() => {
      vi.advanceTimersByTime(19_000);
    });
    expect(result.current.time).toBe('10:30');
    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    expect(result.current.time).toBe('10:31');
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(result.current.time).toBe('10:32');
  });

  it('leaves no timer behind', () => {
    const { unmount } = renderHook(() => useWallClock('Europe/Paris'));

    unmount();

    expect(vi.getTimerCount()).toBe(0);
  });
});
