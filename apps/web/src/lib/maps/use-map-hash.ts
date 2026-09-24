'use client';

/**
 * The URL fragment of a map page, as React state.
 *
 * A map's selection IS its hash: `#f.chat` opens that brick, `#adr-263` points
 * at that decision, `#t.redis` filters the history by that brick. Reading the
 * fragment through `useSyncExternalStore` keeps the page and the address bar
 * from ever disagreeing, and needs no effect to "sync" them: the server renders
 * with no fragment, the client picks it up right after hydration, a followed
 * link fires `hashchange`, and the page's own writes (`setMapHash`) notify the
 * same subscribers — `history.replaceState` fires nothing on its own, and
 * replacing (not pushing) keeps the back button for real navigation.
 */

import { useSyncExternalStore } from 'react';

const listeners = new Set<() => void>();

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  window.addEventListener('hashchange', onChange);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener('hashchange', onChange);
  };
}

/** The fragment without its `#`, decoded — '' when absent or unreadable. */
function readHash(): string {
  const raw = window.location.hash.slice(1);
  try {
    return decodeURIComponent(raw);
  } catch {
    // A hand-typed fragment with a stray `%` is no address of ours.
    return '';
  }
}

const readServerHash = (): string => '';

/** The current fragment of the page, without its `#`. */
export function useMapHash(): string {
  return useSyncExternalStore(subscribe, readHash, readServerHash);
}

/** Replace the fragment (or clear it with null) and tell every reader. */
export function setMapHash(id: string | null): void {
  const { pathname, search } = window.location;
  window.history.replaceState(null, '', id ? `#${encodeURIComponent(id)}` : `${pathname}${search}`);
  listeners.forEach(listener => listener());
}
