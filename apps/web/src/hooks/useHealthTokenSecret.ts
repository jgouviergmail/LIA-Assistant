'use client';

import { useCallback } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import type { useHealthMetrics } from '@/hooks/useHealthMetrics';

/** A source-issued secret belongs only to the account lifetime that requested it. */
export function useHealthTokenSecret(
  createToken: ReturnType<typeof useHealthMetrics>['createToken']
) {
  const { user } = useAuth();
  const { isCurrent } = useApplicationAccountLifetime(user?.id);
  const [secret, setSecret] = useApplicationAccountState<string | null>(user?.id, null);
  const issue = useCallback(
    async (label?: string) => {
      if (!isCurrent()) return;
      const created = await createToken(label);
      if (!isCurrent()) return;
      if (!created) return false;
      setSecret(created.token);
      return true;
    },
    [createToken, isCurrent, setSecret]
  );
  const clear = useCallback(() => {
    setSecret(null);
  }, [setSecret]);
  return { secret, issue, clear };
}
