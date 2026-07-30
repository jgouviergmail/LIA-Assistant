/**
 * Pure-math and subscription behavior of the shared cosmos scroll plumbing.
 */

import { renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { clamp01, sectionProgress, useCosmosScroll } from '../useCosmosScroll';

describe('clamp01', () => {
  it('clamps below, inside and above the unit interval', () => {
    expect(clamp01(-3)).toBe(0);
    expect(clamp01(0.42)).toBe(0.42);
    expect(clamp01(7)).toBe(1);
  });
});

describe('sectionProgress', () => {
  const viewportH = 900;

  it('is 0 while the section top sits at the fold', () => {
    expect(sectionProgress({ top: 900, height: 600 }, viewportH)).toBe(0);
  });

  it('is 1 once the section has fully left through the top', () => {
    expect(sectionProgress({ top: -600, height: 600 }, viewportH)).toBe(1);
  });

  it('is 0.5 at the symmetric middle of the traversal', () => {
    // Traversal spans viewportH + height = 1500px; midpoint at top = 150.
    expect(sectionProgress({ top: 150, height: 600 }, viewportH)).toBeCloseTo(0.5);
  });

  it('clamps outside the traversal window', () => {
    expect(sectionProgress({ top: 5000, height: 600 }, viewportH)).toBe(0);
    expect(sectionProgress({ top: -5000, height: 600 }, viewportH)).toBe(1);
  });
});

describe('useCosmosScroll', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('subscribes passively, fires once on mount, and cleans up on unmount', () => {
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      cb(0);
      return 0;
    });
    const addSpy = vi.spyOn(window, 'addEventListener');
    const removeSpy = vi.spyOn(window, 'removeEventListener');
    const callback = vi.fn();

    const { unmount } = renderHook(() => useCosmosScroll(callback));

    expect(callback).toHaveBeenCalledTimes(1);
    expect(addSpy).toHaveBeenCalledWith('scroll', expect.any(Function), { passive: true });
    expect(addSpy).toHaveBeenCalledWith('resize', expect.any(Function));

    window.dispatchEvent(new Event('scroll'));
    expect(callback).toHaveBeenCalledTimes(2);

    unmount();
    expect(removeSpy).toHaveBeenCalledWith('scroll', expect.any(Function));
    expect(removeSpy).toHaveBeenCalledWith('resize', expect.any(Function));

    window.dispatchEvent(new Event('scroll'));
    expect(callback).toHaveBeenCalledTimes(2);
  });

  it('coalesces bursts of scroll events into one frame', () => {
    const frames: FrameRequestCallback[] = [];
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      frames.push(cb);
      return frames.length;
    });
    const callback = vi.fn();

    renderHook(() => useCosmosScroll(callback));
    // Mount schedules one frame; three more scrolls must NOT schedule more
    // until the pending frame runs.
    window.dispatchEvent(new Event('scroll'));
    window.dispatchEvent(new Event('scroll'));
    window.dispatchEvent(new Event('scroll'));
    expect(frames).toHaveLength(1);

    frames[0](0);
    expect(callback).toHaveBeenCalledTimes(1);

    window.dispatchEvent(new Event('scroll'));
    expect(frames).toHaveLength(2);
  });
});
