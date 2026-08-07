/**
 * Keep the newest content in view as it arrives.
 *
 * For sequences a reader watches unfold rather than scrolls through: the
 * guided showroom missions reveal their sources, then their planning, then
 * one decision card at a time, and a visitor used to chase the storyboard
 * down the page by hand (owner request 2026-08-07).
 *
 * Attach the returned ref to a sentinel placed AFTER the content, and give
 * that sentinel a `scroll-mb-*` class: `scrollIntoView` honours scroll-margin,
 * which is how the requested breathing room below the latest element is
 * obtained without a spacer element that would show up as empty space at rest.
 *
 * Not a substitute for the chat's auto-scroll: that one arbitrates a reading
 * invariant over a paginated, prepend-capable list inside its own scroller.
 * This one follows an append-only sequence in normal document flow.
 */

import { useEffect, useRef } from 'react';

export interface FollowLatestOptions {
  /**
   * Nothing is scrolled while false. A page that has not started its sequence
   * must not move a reader who has not read anything yet.
   */
  active: boolean;
  /** Animate the move. Pass the negation of `prefers-reduced-motion`. */
  smooth: boolean;
}

/**
 * @param marker - Changes exactly when new content has been appended. Anything
 *   comparable with `Object.is` works; a string built from the sequence state
 *   is usually the clearest, since it makes "what counts as new" explicit at
 *   the call site rather than hidden in a dependency array.
 */
export function useFollowLatest(
  marker: unknown,
  { active, smooth }: FollowLatestOptions
): React.RefObject<HTMLDivElement | null> {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!active) return;
    const sentinel = ref.current;
    // Absent in jsdom and in older Safari. A missing scroll is a nuisance; an
    // exception thrown from an effect takes the whole subtree down with it.
    if (typeof sentinel?.scrollIntoView !== 'function') return;
    sentinel.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto', block: 'end' });
  }, [marker, active, smooth]);

  return ref;
}
