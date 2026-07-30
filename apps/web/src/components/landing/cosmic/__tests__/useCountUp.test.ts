/**
 * useCountUp: SSR-safe final initial value, animated replay from zero on
 * start(), locale-correct formatting, reduced-motion instant finish.
 */

import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useCountUp } from '../useCountUp';

/** Installs controllable time: rAF fires immediately with the stubbed clock. */
function installClock() {
  let now = 0;
  const pending: FrameRequestCallback[] = [];
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
    pending.push(cb);
    return pending.length;
  });
  vi.spyOn(performance, 'now').mockImplementation(() => now);
  return {
    advance(ms: number) {
      now += ms;
      const batch = pending.splice(0);
      batch.forEach(cb => cb(now));
    },
  };
}

describe('useCountUp', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('initially displays the final formatted value (SSR / no-JS safety)', () => {
    const { result } = renderHook(() => useCountUp(99, { suffix: '+' }));
    expect(result.current.display).toBe('99+');
  });

  it('replays from zero and lands exactly on the formatted target', () => {
    const clock = installClock();
    const { result } = renderHook(() => useCountUp(99, { suffix: '+', durationMs: 1000 }));

    act(() => result.current.start());
    expect(result.current.display).toBe('0+');

    act(() => clock.advance(500));
    const midway = parseInt(result.current.display, 10);
    expect(midway).toBeGreaterThan(0);
    expect(midway).toBeLessThan(99);

    act(() => clock.advance(600));
    expect(result.current.display).toBe('99+');
  });

  it('formats decimals with the requested locale (fr comma)', () => {
    const clock = installClock();
    const { result } = renderHook(() =>
      useCountUp(0.001, { decimals: 3, suffix: ' €', locale: 'fr', durationMs: 100 })
    );
    expect(result.current.display).toBe('0,001 €');
    act(() => result.current.start());
    act(() => clock.advance(150));
    expect(result.current.display).toBe('0,001 €');
  });

  it('start() is idempotent', () => {
    const clock = installClock();
    const { result } = renderHook(() => useCountUp(50, { durationMs: 100 }));
    act(() => result.current.start());
    act(() => clock.advance(150));
    expect(result.current.display).toBe('50');
    act(() => result.current.start());
    expect(result.current.display).toBe('50');
  });

  it('keeps the final value without motion under prefers-reduced-motion', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockImplementation((query: string) => ({
        matches: query.includes('prefers-reduced-motion'),
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        onchange: null,
        dispatchEvent: vi.fn(),
      }))
    );
    const rafSpy = vi.fn();
    vi.stubGlobal('requestAnimationFrame', rafSpy);
    const { result } = renderHook(() => useCountUp(42));
    act(() => result.current.start());
    expect(result.current.display).toBe('42');
    expect(rafSpy).not.toHaveBeenCalled();
  });
});
