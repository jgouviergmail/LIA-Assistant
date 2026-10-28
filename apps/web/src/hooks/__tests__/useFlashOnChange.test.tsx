import { StrictMode } from 'react';
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useFlashOnChange } from '../useFlashOnChange';

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

describe('useFlashOnChange', () => {
  it('stays down on the first render, Strict Mode included', () => {
    const { result } = renderHook(() => useFlashOnChange('a', 1000), { wrapper: StrictMode });

    expect(result.current).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('rises on the render of the change and falls after the delay', () => {
    const { result, rerender } = renderHook(({ cue }) => useFlashOnChange(cue, 1000), {
      initialProps: { cue: 'a' },
    });

    rerender({ cue: 'b' });

    expect(result.current).toBe(true);
    act(() => vi.advanceTimersByTime(999));
    expect(result.current).toBe(true);
    act(() => vi.advanceTimersByTime(1));
    expect(result.current).toBe(false);
  });

  it('keeps the flag up for the full delay after the latest change', () => {
    const { result, rerender } = renderHook(({ cue }) => useFlashOnChange(cue, 1000), {
      initialProps: { cue: 0 },
    });
    rerender({ cue: 1 });
    act(() => vi.advanceTimersByTime(600));

    rerender({ cue: 2 });
    act(() => vi.advanceTimersByTime(600));

    expect(result.current).toBe(true);
    act(() => vi.advanceTimersByTime(400));
    expect(result.current).toBe(false);
  });

  it('ignores a render that changes nothing and leaves no timer behind on unmount', () => {
    const { result, rerender, unmount } = renderHook(({ cue }) => useFlashOnChange(cue, 1000), {
      initialProps: { cue: 'a' },
    });
    rerender({ cue: 'a' });
    expect(result.current).toBe(false);

    rerender({ cue: 'b' });
    unmount();

    expect(vi.getTimerCount()).toBe(0);
  });
});
