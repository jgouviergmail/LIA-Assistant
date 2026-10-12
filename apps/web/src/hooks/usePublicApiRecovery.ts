'use client';

import { useCallback, useEffect, useRef } from 'react';
import { ApiError } from '@/lib/api-client';

const RECOVERY_DELAYS = [1000, 2000, 4000, 8000, 16000, 30000] as const;

function isTransient(error: Error | null): boolean {
  if (error instanceof ApiError) return [502, 503, 504].includes(error.status);
  return (
    !!error &&
    /failed to fetch|networkerror|load failed|fetch failed|network request failed|timed out|timeout/i.test(
      error.message
    )
  );
}

interface PublicReadRecovery {
  hasData: boolean;
  loading: boolean;
  error: Error | null;
  refetchVerified: () => Promise<boolean>;
}

/** Recovery is for public GET availability only; it never repeats a mutation. */
export function usePublicApiRecovery({
  hasData,
  loading,
  error,
  refetchVerified,
}: PublicReadRecovery) {
  const attempts = useRef(0);
  const running = useRef(false);
  const read = useCallback(() => {
    if (running.current) return;
    running.current = true;
    void refetchVerified()
      .finally(() => {
        running.current = false;
      })
      .catch(() => undefined);
  }, [refetchVerified]);
  useEffect(() => {
    if (hasData) {
      attempts.current = 0;
      return;
    }
    if (loading || !isTransient(error) || attempts.current >= RECOVERY_DELAYS.length) return;
    const timer = window.setTimeout(() => {
      attempts.current += 1;
      read();
    }, RECOVERY_DELAYS[attempts.current]);
    return () => window.clearTimeout(timer);
  }, [hasData, loading, error, read]);

  useEffect(() => {
    if (loading || !isTransient(error)) return;
    let current = true;
    const recover = () => {
      if (!current || document.visibilityState === 'hidden') return;
      read();
    };
    window.addEventListener('online', recover);
    window.addEventListener('focus', recover);
    document.addEventListener('visibilitychange', recover);
    return () => {
      current = false;
      window.removeEventListener('online', recover);
      window.removeEventListener('focus', recover);
      document.removeEventListener('visibilitychange', recover);
    };
  }, [loading, error, read]);
}
