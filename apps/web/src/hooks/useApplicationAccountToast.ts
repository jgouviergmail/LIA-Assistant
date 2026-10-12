'use client';

import { useCallback, useMemo } from 'react';
import { toast } from 'sonner';
import { useApplicationAccountLifetime } from './useApplicationAccountLifetime';

/** Pending settings feedback belongs to the account that initiated the request. */
export function useApplicationAccountToast(ownerId: string | undefined) {
  const { isCurrent } = useApplicationAccountLifetime(ownerId);
  const present = useCallback(
    (kind: 'success' | 'error' | 'info', message: string) => {
      if (isCurrent()) toast[kind](message);
    },
    [isCurrent]
  );
  return useMemo(
    () => ({
      success: (message: string) => present('success', message),
      error: (message: string) => present('error', message),
      info: (message: string) => present('info', message),
    }),
    [present]
  );
}
