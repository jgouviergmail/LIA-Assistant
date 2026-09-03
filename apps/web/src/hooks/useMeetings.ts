'use client';

/**
 * Meetings list and detail (ADR-258).
 *
 * `useMeetingList` pages the user's meetings with the exact total the API
 * returns. `useMeeting` reads one meeting and keeps polling while it is
 * `stopped`/`processing` or regenerating (`stage` set on a `ready` row), then
 * stops — the page shows a live progression without a stream to subscribe to.
 * Every action re-reads the row from the response so the page never guesses.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { useStaleGuard } from '@/hooks/useStaleGuard';
import { ApiError } from '@/lib/api-client';
import { MEETING_STATUS_POLL_MS } from '@/lib/constants';
import { logger } from '@/lib/logger';
import { meetingsApi } from '@/lib/meetings/api';
import {
  IN_FLIGHT_MEETING_STATUSES,
  type MeetingBulkDeleteResponse,
  type MeetingDetail,
  type MeetingPatchRequest,
  type MeetingReformatRequest,
  type MeetingReformatResponse,
  type MeetingSummary,
} from '@/types/meetings';

export interface UseMeetingListReturn {
  meetings: MeetingSummary[];
  total: number;
  isLoading: boolean;
  /** The feature is off (router absent → 404): callers render nothing. */
  isUnavailable: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
  /** True while a bulk delete request is in flight. */
  isDeleting: boolean;
  /**
   * Delete several meetings. Resolves with the server's per-id answer; rejects
   * when the request itself failed (the caller shows the error). It does NOT
   * refetch — the caller decides between a refetch and a page step.
   */
  bulkDelete: (ids: string[]) => Promise<MeetingBulkDeleteResponse>;
}

/** Whether the detail page must keep re-reading this meeting. */
export function isMeetingInFlight(meeting: Pick<MeetingDetail, 'status' | 'stage'>): boolean {
  return IN_FLIGHT_MEETING_STATUSES.includes(meeting.status) || meeting.stage !== null;
}

export function useMeetingList(limit: number, offset = 0, enabled = true): UseMeetingListReturn {
  const [meetings, setMeetings] = useState<MeetingSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(enabled);
  const [isUnavailable, setIsUnavailable] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const guard = useStaleGuard();

  const refetch = useCallback(async () => {
    if (!enabled) return;
    const isStale = guard.begin();
    try {
      const page = await meetingsApi.list(limit, offset);
      if (isStale()) return;
      setMeetings(page.items);
      setTotal(page.total);
      setError(null);
    } catch (err) {
      if (isStale()) return;
      if (err instanceof ApiError && err.status === 404) {
        setIsUnavailable(true);
        setMeetings([]);
        return;
      }
      setError(err instanceof Error ? err : new Error(String(err)));
      logger.error('meetings_list_failed', err as Error, { component: 'useMeetingList' });
    } finally {
      if (!isStale()) setIsLoading(false);
    }
  }, [enabled, guard, limit, offset]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  const bulkDelete = useCallback(async (ids: string[]) => {
    setIsDeleting(true);
    try {
      return await meetingsApi.bulkDelete(ids);
    } catch (err) {
      logger.error('meetings_bulk_delete_failed', err as Error, { component: 'useMeetingList' });
      throw err;
    } finally {
      setIsDeleting(false);
    }
  }, []);

  return { meetings, total, isLoading, isUnavailable, error, refetch, isDeleting, bulkDelete };
}

export interface UseMeetingReturn {
  meeting: MeetingDetail | null;
  isLoading: boolean;
  isNotFound: boolean;
  error: Error | null;
  /** True while an action request is in flight. */
  isActing: boolean;
  refetch: () => Promise<void>;
  patch: (request: MeetingPatchRequest) => Promise<MeetingDetail | null>;
  resetReport: () => Promise<MeetingDetail | null>;
  regenerate: () => Promise<void>;
  /**
   * Write the minutes again with another template (ADR-259). `replace`
   * re-reads this meeting; `new` answers with the derived meeting — the
   * caller navigates there.
   */
  reformat: (request: MeetingReformatRequest) => Promise<MeetingReformatResponse | null>;
  retry: () => Promise<void>;
  email: () => Promise<MeetingDetail | null>;
  deleteTranscript: () => Promise<MeetingDetail | null>;
  remove: () => Promise<boolean>;
}

export function useMeeting(id: string | null, includeTranscript = false): UseMeetingReturn {
  const [meeting, setMeeting] = useState<MeetingDetail | null>(null);
  const [isLoading, setIsLoading] = useState(id !== null);
  const [isNotFound, setIsNotFound] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [isActing, setIsActing] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const guard = useStaleGuard();

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const refetch = useCallback(async () => {
    if (id === null) return;
    const isStale = guard.begin();
    try {
      const detail = await meetingsApi.detail(id, includeTranscript);
      if (isStale()) return;
      setMeeting(detail);
      setError(null);
      setIsNotFound(false);
    } catch (err) {
      if (isStale()) return;
      if (err instanceof ApiError && err.status === 404) {
        setIsNotFound(true);
        return;
      }
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      if (!isStale()) setIsLoading(false);
    }
  }, [guard, id, includeTranscript]);

  // Poll while the server is still working on the meeting; stop as soon as it
  // is not. The refetch after an action re-arms this through `meeting`.
  useEffect(() => {
    clearTimer();
    if (meeting && isMeetingInFlight(meeting)) {
      timerRef.current = setTimeout(() => void refetch(), MEETING_STATUS_POLL_MS);
    }
    return clearTimer;
  }, [meeting, refetch, clearTimer]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  const act = useCallback(async <T>(operation: () => Promise<T>): Promise<T | null> => {
    setIsActing(true);
    try {
      return await operation();
    } finally {
      setIsActing(false);
    }
  }, []);

  const applyDetail = useCallback((detail: MeetingDetail) => {
    setMeeting(detail);
    return detail;
  }, []);

  const patch = useCallback(
    (request: MeetingPatchRequest) =>
      id === null
        ? Promise.resolve(null)
        : act(async () => applyDetail(await meetingsApi.patch(id, request))),
    [act, applyDetail, id]
  );
  const resetReport = useCallback(
    () =>
      id === null
        ? Promise.resolve(null)
        : act(async () => applyDetail(await meetingsApi.resetReport(id))),
    [act, applyDetail, id]
  );
  const email = useCallback(
    () =>
      id === null
        ? Promise.resolve(null)
        : act(async () => applyDetail(await meetingsApi.email(id))),
    [act, applyDetail, id]
  );
  const deleteTranscript = useCallback(
    () =>
      id === null
        ? Promise.resolve(null)
        : act(async () => applyDetail(await meetingsApi.deleteTranscript(id))),
    [act, applyDetail, id]
  );
  const regenerate = useCallback(async () => {
    if (id === null) return;
    await act(async () => {
      await meetingsApi.regenerate(id);
      await refetch();
    });
  }, [act, id, refetch]);
  const reformat = useCallback(
    async (request: MeetingReformatRequest) => {
      if (id === null) return null;
      return act(async () => {
        const response = await meetingsApi.reformat(id, request);
        if (request.mode === 'replace') await refetch();
        return response;
      });
    },
    [act, id, refetch]
  );
  const retry = useCallback(async () => {
    if (id === null) return;
    await act(async () => {
      await meetingsApi.retry(id);
      await refetch();
    });
  }, [act, id, refetch]);
  const remove = useCallback(async () => {
    if (id === null) return false;
    const done = await act(async () => {
      await meetingsApi.remove(id);
      return true;
    });
    return done === true;
  }, [act, id]);

  return {
    meeting,
    isLoading,
    isNotFound,
    error,
    isActing,
    refetch,
    patch,
    resetReport,
    regenerate,
    reformat,
    retry,
    email,
    deleteTranscript,
    remove,
  };
}
