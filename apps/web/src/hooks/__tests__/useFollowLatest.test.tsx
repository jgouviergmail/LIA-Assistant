/**
 * useFollowLatest — keep the newest content in view as it arrives.
 *
 * Owner request 2026-08-07, on the guided missions: "un scroll automatique
 * afin de toujours avoir les derniers éléments affichés visibles à l'écran
 * avec une marge basse suffisante". A mission reveals its sources, its
 * planning, then each decision card one after another; a visitor watching the
 * storyboard had to chase it down the page by hand.
 *
 * The behaviour worth testing is *when* it scrolls, not *that* the browser
 * scrolls — jsdom has no layout. So: it follows a new marker, it stays put
 * while nothing changes, it never moves before it is armed, and it obeys
 * reduced motion.
 */

import { render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useFollowLatest } from '@/hooks/useFollowLatest';

const scrollIntoView = vi.fn();

beforeEach(() => {
  scrollIntoView.mockClear();
  Object.defineProperty(Element.prototype, 'scrollIntoView', {
    configurable: true,
    writable: true,
    value: scrollIntoView,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

function Follower({
  marker,
  active = true,
  smooth = true,
}: {
  marker: string;
  active?: boolean;
  smooth?: boolean;
}) {
  const ref = useFollowLatest(marker, { active, smooth });
  return <div ref={ref} data-testid="sentinel" />;
}

describe('useFollowLatest', () => {
  it('brings the sentinel into view when the marker changes', () => {
    const { rerender } = render(<Follower marker="sources:1" />);
    scrollIntoView.mockClear();

    rerender(<Follower marker="sources:2" />);

    expect(scrollIntoView).toHaveBeenCalledTimes(1);
  });

  it('stays where it is when nothing new arrived', () => {
    const { rerender } = render(<Follower marker="sources:1" />);
    scrollIntoView.mockClear();

    // A re-render for any other reason — a translation loading, a parent
    // updating — must not yank the viewport.
    rerender(<Follower marker="sources:1" />);

    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it('never scrolls before it is armed', () => {
    // A mission that has not started yet is just a page: scrolling on mount
    // would move a visitor who has read nothing.
    const { rerender } = render(<Follower marker="ready" active={false} />);

    rerender(<Follower marker="reading_sources" active={false} />);

    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it('catches up as soon as it is armed', () => {
    const { rerender } = render(<Follower marker="ready" active={false} />);

    rerender(<Follower marker="ready" active />);

    expect(scrollIntoView).toHaveBeenCalledTimes(1);
  });

  it('anchors on the END of the sentinel, so what is below it stays visible', () => {
    const { rerender } = render(<Follower marker="a" />);
    scrollIntoView.mockClear();

    rerender(<Follower marker="b" />);

    expect(scrollIntoView).toHaveBeenCalledWith(expect.objectContaining({ block: 'end' }));
  });

  it('animates by default', () => {
    const { rerender } = render(<Follower marker="a" />);
    scrollIntoView.mockClear();

    rerender(<Follower marker="b" />);

    expect(scrollIntoView).toHaveBeenCalledWith(expect.objectContaining({ behavior: 'smooth' }));
  });

  it('jumps instead of animating under reduced motion', () => {
    const { rerender } = render(<Follower marker="a" smooth={false} />);
    scrollIntoView.mockClear();

    rerender(<Follower marker="b" smooth={false} />);

    expect(scrollIntoView).toHaveBeenCalledWith(expect.objectContaining({ behavior: 'auto' }));
  });

  it('survives a browser without scrollIntoView rather than crashing the page', () => {
    // Older Safari and jsdom both lack it. A missing scroll is a nuisance; an
    // exception thrown from an effect unmounts the mission.
    Object.defineProperty(Element.prototype, 'scrollIntoView', {
      configurable: true,
      writable: true,
      value: undefined,
    });

    const { rerender } = render(<Follower marker="a" />);

    expect(() => rerender(<Follower marker="b" />)).not.toThrow();
  });
});
