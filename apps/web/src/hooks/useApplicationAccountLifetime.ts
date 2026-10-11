'use client';

import { useCallback, useEffect, useMemo, useRef } from 'react';

export interface ApplicationAccountLifetime {
  readonly ownerId: string | undefined;
}

/** Returning to the same account starts a new lifetime for local edits and callbacks. */
export function useApplicationAccountLifetime(ownerId: string | undefined) {
  const lifetime = useMemo<ApplicationAccountLifetime>(() => ({ ownerId }), [ownerId]);
  const active = useRef<ApplicationAccountLifetime | null>(lifetime);
  useEffect(() => {
    active.current = lifetime;
    return () => {
      active.current = null;
    };
  }, [lifetime]);
  const isCurrent = useCallback(
    () => !!lifetime.ownerId && active.current === lifetime,
    [lifetime]
  );
  return { lifetime, isCurrent };
}
