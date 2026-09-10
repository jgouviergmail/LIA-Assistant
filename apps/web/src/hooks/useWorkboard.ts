'use client';
/**
 * The board, and every write that changes it (ADR-276).
 *
 * The board's rows and its EXACT totals live in a pure reducer
 * (`reducers/workboard-reducer.ts`); this hook owns the I/O around it and
 * nothing else. Four contracts, each of them a defect this repository has
 * already paid for:
 *
 * - **A refresh is not a first load.** `firstLoad` is derived from the ABSENCE
 *   of a payload, never from `error` — a refetch clears the error, and a
 *   spinner keyed on it unmounts the board mid-refresh and takes the reader's
 *   place with it (`PeerConnectionsSettings`, 2026-07-31).
 * - **A verb answers, it never throws.** Every write resolves
 *   `{ok, errorCode}` with the backend's STABLE `workboard_*` code, so the
 *   caller translates a code and never a sentence, and no caller can forget a
 *   `catch`.
 * - **A move is optimistic and its rollback is EXACT.** The snapshot taken
 *   before the move is what comes back — order included, not just membership.
 * - **What changes rows this page cannot see is RE-READ.** Creation and
 *   deletion touch children in other columns and rows past the page, so their
 *   counts are re-read rather than guessed (ADR-185).
 */
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';

import { useStaleGuard } from '@/hooks/useStaleGuard';
import { ApiError } from '@/lib/api-client';
import { workboardApi } from '@/lib/workboard/api';
import {
  initialWorkboardState,
  ticketsOf,
  workboardReducer,
  type WorkboardState,
} from '@/reducers/workboard-reducer';
import type {
  BoardFilters,
  TicketCreateBody,
  TicketRow,
  TicketUpdateBody,
} from '@/types/workboard';

/** What a write answers: it succeeded, or it was refused with a stable code. */
export interface WriteOutcome {
  ok: boolean;
  /** The backend's `workboard_*` code, or null when the failure had no shape. */
  errorCode: string | null;
}

export interface UseWorkboardResult {
  tickets: TicketRow[];
  countsByStatus: Record<string, number>;
  /** Exact number of tickets the filter matches, page or no page. */
  total: number;
  /** The cards of one column, ordered. */
  column: (status: string) => TicketRow[];
  /** True only before the first payload — never on a refetch. */
  firstLoad: boolean;
  loading: boolean;
  error: Error | null;
  /** The instance flag is off (the router answers 404): callers render nothing. */
  isUnavailable: boolean;
  refetch: () => Promise<void>;
  move: (id: string, status: string, position: number) => Promise<WriteOutcome>;
  patch: (id: string, body: TicketUpdateBody) => Promise<WriteOutcome>;
  create: (body: TicketCreateBody) => Promise<WriteOutcome>;
  comment: (id: string, body: string) => Promise<WriteOutcome>;
  runNow: (id: string) => Promise<WriteOutcome>;
  remove: (id: string) => Promise<WriteOutcome>;
}

/**
 * The stable `workboard_*` code behind a rejection, when it carries one.
 *
 * @param error - Whatever the call rejected with.
 * @returns The code, or null — a raw message must never reach the screen.
 */
export function workboardErrorCode(error: unknown): string | null {
  if (error instanceof ApiError && error.data && typeof error.data === 'object') {
    const detail = (error.data as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
  }
  return null;
}

/**
 * How often the board re-reads itself while nobody touches it.
 *
 * The sweep runs at most one ticket a minute, so half a minute is the finest
 * grain that can show anything new; anything shorter would be a request per
 * reader for a board that had not moved.
 */
const AUTO_REFRESH_MS = 30_000;

export function useWorkboard(
  filters: BoardFilters = {},
  options: { paused?: boolean } = {}
): UseWorkboardResult {
  const [state, dispatch] = useReducer(workboardReducer, initialWorkboardState);
  const [firstLoad, setFirstLoad] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [isUnavailable, setIsUnavailable] = useState(false);
  const guard = useStaleGuard();

  // Two LATEST-VALUE refs, updated POST-COMMIT like `useApiQuery` does: a ref
  // written during render is a render-phase side effect React is free to
  // discard, and the linter refuses it.
  //
  // `filtersRef` keeps `refetch` stable — the filters are an object literal at
  // every call site — so the focus listener below is installed once instead of
  // on every render. `stateRef` is what `move` snapshots: a closure over
  // `state` would capture the board as it was when that closure was BUILT, so
  // two moves fired before the first answer would share one snapshot and the
  // rollback of the second would undo the first.
  const filtersRef = useRef(filters);
  const stateRef = useRef(state);
  // Two reasons a poll must stand aside, both of them « no impact »: a drag in
  // progress (the caller says so) and a write whose answer has not landed yet.
  const pausedRef = useRef(false);
  const writesInFlight = useRef(0);
  const paused = options.paused ?? false;
  useEffect(() => {
    filtersRef.current = filters;
    stateRef.current = state;
    // Post-commit like the two above, and for the same reason: a ref written
    // during render belongs to an arbitrary attempt React is free to discard.
    // The poll only reads it on a 30 s timer, so a commit's delay is nothing.
    pausedRef.current = paused;
  });
  const filterKey = JSON.stringify(filters);

  const read = useCallback(
    async (quiet: boolean) => {
      const isStale = guard.begin();
      // A QUIET read never touches `loading`: that flag spins the refresh
      // button and drives `aria-busy`, so a background poll announcing itself
      // every thirty seconds would be the opposite of « without impact ».
      if (!quiet) setLoading(true);
      try {
        const page = await workboardApi.board(filtersRef.current);
        if (isStale()) return;
        dispatch({ type: 'loaded', page });
        setError(null);
        setIsUnavailable(false);
      } catch (caught) {
        if (isStale()) return;
        // The router is absent when the instance flag is off, so a 404 is a
        // CONFIGURATION answer, not a failure to report.
        if (caught instanceof ApiError && caught.status === 404) {
          setIsUnavailable(true);
          setError(null);
          return;
        }
        // A poll that fails changes nothing on screen: the board on display is
        // still the last one the server confirmed, and turning a lost second
        // into an error page would be a worse lie than showing it a minute old.
        if (quiet) return;
        setError(caught instanceof Error ? caught : new Error(String(caught)));
      } finally {
        if (!isStale() && !quiet) {
          setLoading(false);
          setFirstLoad(false);
        }
      }
    },
    [guard]
  );

  const refetch = useCallback(() => read(false), [read]);

  useEffect(() => {
    void refetch();
    // `filterKey` is the VALUE of the filters, not their identity: a literal
    // rebuilt on every render would otherwise re-fetch forever.
  }, [refetch, filterKey]);

  // Nothing pushes a peer's change to this tab (ADR-276 leaves real-time sync
  // out of scope), so coming back to it is when the board re-reads.
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible') void refetch();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [refetch]);

  // The board moves on its own — the sweep runs a ticket every minute — so it
  // re-reads on its own too. Three things make it « without impact »: the read
  // is QUIET (no spinner, no `aria-busy`, no error page), it stands aside while
  // the person is dragging a card or a write is still in flight (a poll landing
  // between an optimistic move and its answer would flip the card back and
  // forth), and a hidden tab reads nothing at all.
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.hidden || pausedRef.current || writesInFlight.current > 0) return;
      void read(true);
    }, AUTO_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [read]);

  /**
   * Hold the auto-refresh for as long as one write is in flight.
   *
   * EVERY write goes through here, optimistic ones included: a poll answering
   * between a move's dispatch and its confirmation would paint the board the
   * server still knows, and the card would visibly jump back before the answer
   * put it right. Counted, not flagged — two writes can overlap (a move while
   * a comment is posting), and a boolean would let the first one to answer
   * re-open the door under the second.
   */
  const duringWrite = useCallback(async <T>(call: () => Promise<T>): Promise<T> => {
    writesInFlight.current += 1;
    try {
      return await call();
    } finally {
      writesInFlight.current -= 1;
    }
  }, []);

  /** Run one write, answering with a code rather than raising. */
  const write = useCallback(
    (call: () => Promise<unknown>, after?: () => void | Promise<void>): Promise<WriteOutcome> =>
      duringWrite(async () => {
        try {
          await call();
          await after?.();
          return { ok: true, errorCode: null };
        } catch (caught) {
          return { ok: false, errorCode: workboardErrorCode(caught) };
        }
      }),
    [duringWrite]
  );

  const move = useCallback(
    async (id: string, status: string, position: number): Promise<WriteOutcome> => {
      // The snapshot is the rollback: restoring it puts every card back at the
      // index it held, which re-deriving an inverse move could only approximate.
      const snapshot: WorkboardState = stateRef.current;
      dispatch({ type: 'moved', id, status, position });
      return duringWrite(async () => {
        try {
          const row = await workboardApi.move(id, { status, position });
          dispatch({ type: 'patched', ticket: row });
          return { ok: true, errorCode: null };
        } catch (caught) {
          dispatch({ type: 'restored', snapshot });
          return { ok: false, errorCode: workboardErrorCode(caught) };
        }
      });
    },
    [duringWrite]
  );

  const patch = useCallback(
    (id: string, body: TicketUpdateBody): Promise<WriteOutcome> =>
      duringWrite(async () => {
        try {
          const row = await workboardApi.update(id, body);
          dispatch({ type: 'patched', ticket: row });
          return { ok: true, errorCode: null };
        } catch (caught) {
          return { ok: false, errorCode: workboardErrorCode(caught) };
        }
      }),
    [duringWrite]
  );

  const runNow = useCallback(
    (id: string): Promise<WriteOutcome> =>
      duringWrite(async () => {
        try {
          const row = await workboardApi.runNow(id);
          dispatch({ type: 'patched', ticket: row });
          return { ok: true, errorCode: null };
        } catch (caught) {
          return { ok: false, errorCode: workboardErrorCode(caught) };
        }
      }),
    [duringWrite]
  );

  const create = useCallback(
    (body: TicketCreateBody) => write(() => workboardApi.create(body), refetch),
    [write, refetch]
  );
  const remove = useCallback(
    (id: string) => write(() => workboardApi.remove(id), refetch),
    [write, refetch]
  );
  // Re-read after a comment: on a « confirming » ticket the owner's comment IS
  // the answer, and the SERVER moves the ticket (back to « to do », held by
  // LIA) — a change this page cannot see without asking (lot 9, and the board
  // that stayed put until the next poll, owner feedback 2026-09-09).
  const comment = useCallback(
    (id: string, body: string) => write(() => workboardApi.comment(id, body), refetch),
    [write, refetch]
  );

  const column = useCallback((status: string) => ticketsOf(state, status), [state]);

  return useMemo(
    () => ({
      tickets: state.tickets,
      countsByStatus: state.countsByStatus,
      total: state.total,
      column,
      firstLoad,
      loading,
      error,
      isUnavailable,
      refetch,
      move,
      patch,
      create,
      comment,
      runNow,
      remove,
    }),
    [
      state,
      column,
      firstLoad,
      loading,
      error,
      isUnavailable,
      refetch,
      move,
      patch,
      create,
      comment,
      runNow,
      remove,
    ]
  );
}
