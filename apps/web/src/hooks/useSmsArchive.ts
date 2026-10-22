'use client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import type { SmsPage, SmsQuery } from '@/types/sms';

interface ReadResult {
  key: string;
  criteria: string;
  page: SmsPage;
  /** When the read that produced it started: a change signalled later outdates it. */
  readAt: number;
}
interface ReadFailure {
  key: string;
  error: Error;
}

function projectRead(
  result: ReadResult | null,
  failure: ReadFailure | null,
  key: string,
  criteria: string,
  retainPage: boolean,
  enabled: boolean,
  loading: boolean
) {
  const current = result?.key === key;
  const error = failure?.key === key ? failure.error : null;
  const retained = retainPage && result?.criteria === criteria;
  return {
    // Retain only a page of the same query. Owner/source changes clear it.
    data: result && (current || retained) ? result.page : null,
    error,
    loading: enabled && (loading || (!current && !error)),
  };
}

/** Search terms stay out of URLs. Every read owns its abort and account lifetime. */
export function useSmsArchive(
  supplied: SmsQuery,
  enabled = true,
  resetCursor?: () => void,
  retainPage = false
) {
  const { user } = useAuth();
  const ownerId = user?.id;
  const { isCurrent, lifetime } = useApplicationAccountLifetime(ownerId);
  const { query: text, sender_id, from_ts, to_ts, limit, cursor } = supplied;
  const query = useMemo(
    () => ({ query: text, sender_id, from_ts, to_ts, limit, cursor }),
    [text, sender_id, from_ts, to_ts, limit, cursor]
  );
  const key = JSON.stringify(query);
  const criteria = JSON.stringify({ text, sender_id, from_ts, to_ts, limit });
  const [result, setResult] = useApplicationAccountState<ReadResult | null>(ownerId, null);
  const [failure, setFailure] = useApplicationAccountState<ReadFailure | null>(ownerId, null);
  const [loading, setLoading] = useApplicationAccountState(ownerId, false);
  // A refresh is not a first load (owner rule 2026-10-21): the page in view
  // stays until its successor lands, so nothing unmounts and no focus is lost.
  const [refreshing, setRefreshing] = useApplicationAccountState(ownerId, false);
  const [revision, setRevision] = useState(0);
  // When a change was last signalled — the page a failed re-read withdraws is
  // one read before it, never a page a failed page turn was leaving.
  const changedAt = useRef(0);
  const { mutate } = useApiMutation<SmsQuery, SmsPage>({
    method: 'POST',
    componentName: 'useSmsArchive',
    retainResponse: false,
  });
  const refresh = useCallback(async () => {
    if (!isCurrent()) return;
    // Back to the first page — a cursor is bound to the data revision a
    // change just moved — while the page in view stays on screen.
    changedAt.current = performance.now();
    setRefreshing(true);
    resetCursor?.();
    setFailure(null);
    setRevision(value => value + 1);
  }, [isCurrent, setFailure, setRefreshing, resetCursor]);
  useApplicationResourceSync(enabled ? ownerId : undefined, 'sms', refresh);
  useEffect(() => {
    if (!enabled || !ownerId) return;
    let current = true;
    const controller = new AbortController();
    void Promise.resolve().then(async () => {
      if (!current) return;
      const readAt = performance.now();
      setLoading(true);
      setFailure(null);
      try {
        const page = await mutate('/sms/search', query, { signal: controller.signal });
        if (current && isCurrent() && page) setResult({ key, criteria, page, readAt });
      } catch (error) {
        if (current && isCurrent()) {
          setFailure({ key, error: error instanceof Error ? error : new Error('SMS read failed') });
          // A page read before the last change cannot be vouched for once its
          // re-read fails — an erasure may be the very change it was reading.
          // A page turn that failed keeps the page it was turning from.
          setResult(previous =>
            previous && previous.readAt < changedAt.current ? null : previous
          );
        }
      } finally {
        if (current) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    });
    return () => {
      current = false;
      controller.abort();
    };
  }, [
    enabled,
    ownerId,
    lifetime,
    query,
    key,
    criteria,
    revision,
    mutate,
    isCurrent,
    setResult,
    setFailure,
    setLoading,
    setRefreshing,
  ]);
  return {
    ...projectRead(
      result,
      failure,
      key,
      criteria,
      retainPage || refreshing,
      enabled && !!ownerId,
      loading
    ),
    refresh,
  };
}
