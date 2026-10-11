'use client';

import { useCallback, useState, type SetStateAction } from 'react';
import { useApplicationAccountLifetime } from './useApplicationAccountLifetime';

/** Concrete local values belong to one account lifetime, including A-to-B-to-A. */
export function useApplicationAccountState<T>(ownerId: string | undefined, initial: T) {
  const { lifetime, isCurrent } = useApplicationAccountLifetime(ownerId);
  const [fallback] = useState({ value: initial });
  const [saved, save] = useState({ lifetime, value: initial });
  const setValue = useCallback(
    (action: SetStateAction<T>) => {
      if (isCurrent())
        save(previous => {
          const value = previous.lifetime === lifetime ? previous.value : fallback.value;
          return {
            lifetime,
            value: typeof action === 'function' ? (action as (previous: T) => T)(value) : action,
          };
        });
    },
    [isCurrent, lifetime, fallback]
  );
  return [saved.lifetime === lifetime ? saved.value : fallback.value, setValue] as const;
}
