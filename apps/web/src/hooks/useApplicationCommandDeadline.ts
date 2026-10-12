'use client';

import { useEffect } from 'react';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';

/** Observe expiry on the clock effect; rendering remains pure across account lifetimes. */
export function useApplicationCommandDeadline(value: string, scopeKey: string | undefined) {
  const [deadline, setDeadline] = useApplicationAccountState<{
    value: string;
    expired: boolean;
  } | null>(scopeKey, null);
  useEffect(() => {
    const remaining = Date.parse(value) - Date.now();
    setDeadline({ value, expired: remaining <= 0 });
    const timer = setTimeout(() => setDeadline({ value, expired: true }), Math.max(0, remaining));
    return () => clearTimeout(timer);
  }, [value, setDeadline]);
  return deadline?.value !== value || deadline.expired;
}
