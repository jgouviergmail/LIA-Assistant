/**
 * Smoke matrix over every /more scene — one contract for all:
 *  - inert when active=false (no timer scheduled: out-of-view cards and the
 *    WCAG 2.2.2 pause really stop the work);
 *  - a full cycle (and one loop) under fake timers runs without throwing;
 *  - unmount leaks no timer;
 *  - reduced motion renders the resting frame with zero timers;
 *  - the merged scene set covers exactly MORE_CARD_KEYS (a card without a
 *    scene — or a scene without a card — fails here, not in production).
 */

import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { MORE_CARD_KEYS } from '../more-data';
import { SCENE_REGISTRY } from '../scene-registry';

/** Any label suffix resolves to itself — scenes never depend on real copy. */
const LABELS = new Proxy({}, { get: (_t, p) => (typeof p === 'string' ? p : '') }) as Record<
  string,
  string
>;

function mockReducedMotion(matches: boolean) {
  vi.spyOn(window, 'matchMedia').mockImplementation(
    (query: string) =>
      ({
        matches: query.includes('prefers-reduced-motion') ? matches : false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        onchange: null,
        dispatchEvent: vi.fn(),
      }) as MediaQueryList
  );
}

describe('scene registry', () => {
  it('covers exactly MORE_CARD_KEYS — no missing, no orphan scene', () => {
    expect(Object.keys(SCENE_REGISTRY).sort()).toEqual([...MORE_CARD_KEYS].sort());
  });
});

describe.each(Object.entries(SCENE_REGISTRY))('scene %s', (_key, Scene) => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockReducedMotion(false);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('mounts inert when inactive (no timer scheduled)', () => {
    render(<Scene active={false} labels={LABELS} />);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('runs a full cycle plus a loop under fake timers and cleans up on unmount', () => {
    const { unmount } = render(<Scene active labels={LABELS} />);
    act(() => vi.advanceTimersByTime(15_000));
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('renders its resting frame under reduced motion with zero timers', () => {
    mockReducedMotion(true);
    const { container } = render(<Scene active labels={LABELS} />);
    expect(container.firstElementChild).not.toBeNull();
    expect(vi.getTimerCount()).toBe(0);
  });
});
