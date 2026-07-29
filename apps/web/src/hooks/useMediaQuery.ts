'use client';

/**
 * useMediaQuery — matchMedia as an external store (no setState-in-effect).
 *
 * SSR/first paint answers `false`: the server cannot know the viewport, and
 * a stable "narrow features off" default avoids a hydration mismatch.
 */

import { useCallback, useSyncExternalStore } from 'react';

export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onStoreChange: () => void) => {
      const mql = window.matchMedia(query);
      mql.addEventListener('change', onStoreChange);
      return () => mql.removeEventListener('change', onStoreChange);
    },
    [query]
  );
  const getSnapshot = useCallback(() => window.matchMedia(query).matches, [query]);
  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}
