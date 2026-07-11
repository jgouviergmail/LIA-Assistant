/**
 * useLiveTabTitle — hidden-tab alternation and exact-restore guarantees.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';

import { useLiveTabTitle } from '../useLiveTabTitle';

let hidden = false;

describe('useLiveTabTitle', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    hidden = false;
    Object.defineProperty(document, 'hidden', {
      configurable: true,
      get: () => hidden,
    });
    document.title = 'LIA - Dashboard';
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('alternates the title while active and hidden', () => {
    hidden = true;
    renderHook(() => useLiveTabTitle(true));

    vi.advanceTimersByTime(1500);
    expect(document.title).toBe('✦ chat.tab_title_writing');

    vi.advanceTimersByTime(1500);
    expect(document.title).toBe('LIA - Dashboard');
  });

  it('does not touch the title while the tab is visible', () => {
    hidden = false;
    renderHook(() => useLiveTabTitle(true));

    vi.advanceTimersByTime(4500);
    expect(document.title).toBe('LIA - Dashboard');
  });

  it('restores the exact title when deactivated mid-blink', () => {
    hidden = true;
    const { rerender } = renderHook(({ active }) => useLiveTabTitle(active), {
      initialProps: { active: true },
    });

    vi.advanceTimersByTime(1500);
    expect(document.title).toBe('✦ chat.tab_title_writing');

    rerender({ active: false });
    expect(document.title).toBe('LIA - Dashboard');
  });

  it('restores the exact title on unmount', () => {
    hidden = true;
    const { unmount } = renderHook(() => useLiveTabTitle(true));

    vi.advanceTimersByTime(1500);
    unmount();
    expect(document.title).toBe('LIA - Dashboard');
  });

  it('does nothing while inactive', () => {
    hidden = true;
    renderHook(() => useLiveTabTitle(false));

    vi.advanceTimersByTime(4500);
    expect(document.title).toBe('LIA - Dashboard');
  });
});
