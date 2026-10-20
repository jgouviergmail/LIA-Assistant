'use client';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import type { SmsPage, SmsQuery } from '@/types/sms';

/** Search terms stay out of URLs. Every read owns its abort and account lifetime. */
export function useSmsArchive(supplied: SmsQuery, enabled = true, resetCursor?: () => void) {
  const { user } = useAuth();
  const { isCurrent, lifetime } = useApplicationAccountLifetime(user?.id);
  const { query: text, sender_id, from_ts, to_ts, limit, cursor } = supplied;
  const query = useMemo(
    () => ({ query: text, sender_id, from_ts, to_ts, limit, cursor }),
    [text, sender_id, from_ts, to_ts, limit, cursor]
  );
  const key = JSON.stringify(query);
  const [result, setResult] = useApplicationAccountState<{ key: string; page: SmsPage } | null>(
    user?.id,
    null
  );
  const [failure, setFailure] = useApplicationAccountState<{ key: string; error: Error } | null>(
    user?.id,
    null
  );
  const [loading, setLoading] = useApplicationAccountState(user?.id, false);
  const [revision, setRevision] = useState(0);
  const { mutate } = useApiMutation<SmsQuery, SmsPage>({
    method: 'POST',
    componentName: 'useSmsArchive',
    retainResponse: false,
  });
  const refresh = useCallback(async () => {
    if (!isCurrent()) return;
    resetCursor?.();
    setResult(null);
    setFailure(null);
    setRevision(value => value + 1);
  }, [isCurrent, setResult, setFailure, resetCursor]);
  useApplicationResourceSync(enabled ? user?.id : undefined, 'sms', refresh);
  useEffect(() => {
    if (!enabled || !user?.id) return;
    let current = true;
    const controller = new AbortController();
    void Promise.resolve().then(async () => {
      if (!current) return;
      setLoading(true);
      setFailure(null);
      try {
        const page = await mutate('/sms/search', query, { signal: controller.signal });
        if (current && isCurrent() && page) setResult({ key, page });
      } catch (error) {
        if (current && isCurrent())
          setFailure({ key, error: error instanceof Error ? error : new Error('SMS read failed') });
      } finally {
        if (current) setLoading(false);
      }
    });
    return () => {
      current = false;
      controller.abort();
    };
  }, [
    enabled,
    user?.id,
    lifetime,
    query,
    key,
    revision,
    mutate,
    isCurrent,
    setResult,
    setFailure,
    setLoading,
  ]);
  return {
    data: result?.key === key ? result.page : null,
    error: failure?.key === key ? failure.error : null,
    loading,
    refresh,
  };
}
