/**
 * Step-up guard (security program D1, Lot 3).
 *
 * Wrap any sensitive mutation with `guard(fn)`: when the backend answers
 * the typed 403 (`step_up_required`), the host component's StepUpDialog
 * opens; after a successful re-authentication the original action is
 * replayed once. Cancelling rejects with the original challenge.
 */

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiStepUpError } from '@/lib/api-client';
import {
  useApplicationAccountLifetime,
  type ApplicationAccountLifetime,
} from './useApplicationAccountLifetime';

interface PendingChallenge {
  lifetime: ApplicationAccountLifetime;
  isCurrent: () => boolean;
  resolve: () => void;
  reject: (error: unknown) => void;
}

export function useStepUpGuard(scope?: { ownerId: string | undefined }) {
  const { lifetime, isCurrent } = useApplicationAccountLifetime(scope?.ownerId);
  const scoped = scope !== undefined;
  const canAct = useCallback(() => !scoped || isCurrent(), [scoped, isCurrent]);
  const [challenge, setChallenge] = useState<PendingChallenge | null>(null);
  const pending = useRef<PendingChallenge | null>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      const cancelled = pending.current;
      pending.current = null;
      cancelled?.reject(new ApiStepUpError());
    };
  }, []);
  useEffect(() => {
    const previous = pending.current;
    if (previous && !previous.isCurrent()) {
      pending.current = null;
      previous.reject(new ApiStepUpError());
    }
  }, [lifetime]);

  const guard = useCallback(
    async <T>(action: () => Promise<T>): Promise<T> => {
      if (!mounted.current || !canAct() || pending.current) throw new ApiStepUpError();
      try {
        return await action();
      } catch (error) {
        if (!(error instanceof ApiStepUpError)) throw error;
        if (!mounted.current || !canAct() || pending.current) throw error;
        // Park the action until the dialog reports a successful step-up.
        await new Promise<void>((resolve, reject) => {
          const next = { resolve, reject, lifetime, isCurrent: canAct };
          pending.current = next;
          setChallenge(next);
        });
        if (!mounted.current || !canAct()) throw new ApiStepUpError();
        return action();
      }
    },
    [canAct, lifetime]
  );

  const onVerified = useCallback(() => {
    if (!mounted.current || !challenge || pending.current !== challenge || !challenge.isCurrent())
      return;
    pending.current = null;
    challenge.resolve();
    setChallenge(null);
  }, [challenge]);

  const onCancel = useCallback(() => {
    if (!mounted.current || !challenge || pending.current !== challenge || !challenge.isCurrent())
      return;
    pending.current = null;
    challenge.reject(new ApiStepUpError());
    setChallenge(null);
  }, [challenge]);

  return {
    guard,
    stepUpOpen: challenge !== null && challenge.lifetime === lifetime,
    onVerified,
    onCancel,
  };
}
