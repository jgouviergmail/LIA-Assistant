/**
 * Step-up guard (security program D1, Lot 3).
 *
 * Wrap any sensitive mutation with `guard(fn)`: when the backend answers
 * the typed 403 (`step_up_required`), the host component's StepUpDialog
 * opens; after a successful re-authentication the original action is
 * replayed once. Cancelling rejects with the original challenge.
 */

'use client';

import { useCallback, useState } from 'react';
import { ApiStepUpError } from '@/lib/api-client';

interface PendingChallenge {
  resolve: () => void;
  reject: (error: unknown) => void;
}

export function useStepUpGuard() {
  const [challenge, setChallenge] = useState<PendingChallenge | null>(null);

  const guard = useCallback(async <T>(action: () => Promise<T>): Promise<T> => {
    try {
      return await action();
    } catch (error) {
      if (!(error instanceof ApiStepUpError)) throw error;
      // Park the action until the dialog reports a successful step-up.
      await new Promise<void>((resolve, reject) => {
        setChallenge({ resolve, reject });
      });
      return action();
    }
  }, []);

  const onVerified = useCallback(() => {
    challenge?.resolve();
    setChallenge(null);
  }, [challenge]);

  const onCancel = useCallback(() => {
    challenge?.reject(new ApiStepUpError());
    setChallenge(null);
  }, [challenge]);

  return { guard, stepUpOpen: challenge !== null, onVerified, onCancel };
}
