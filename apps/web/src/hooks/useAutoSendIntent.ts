'use client';

/**
 * useAutoSendIntent — the `?intent=` half of the QW-24 contract (ADR-173).
 *
 * `?draft=` prefills and NEVER sends (A4 contract, untouched). `?intent=`
 * EXECUTES: the click on a named card action was the deliberate act, so the
 * request is sent through the exact path a typed message takes
 * (`sendMessageFromPresent` — the W3-retry rule: never a second, subtly
 * different send route).
 *
 * Consumed once (StrictMode-proof via ref; the page strips the param from
 * the URL separately so a reload never re-sends). While the composer is
 * busy (`isTyping` — e.g. a background run streaming) or the API is not
 * reachable yet, the effect simply retries on the next state change. A
 * usage-blocked session degrades to a persisted draft — the request is
 * saved, never silently dropped, and never force-fed past a quota wall.
 */

import { useEffect, useRef } from 'react';

export interface UseAutoSendIntentArgs {
  /** The decoded `?intent=` value captured at mount ('' = none). */
  intent: string;
  /** True once auth is resolved (the layout redirects unauthenticated). */
  ready: boolean;
  apiAvailable: boolean;
  isTyping: boolean;
  isUsageBlocked: boolean;
  /** The page's `sendMessageFromPresent`. */
  send: (text: string) => void | Promise<unknown>;
  /** Quota-wall fallback: persist as draft + tell the user (no send). */
  fallbackToDraft: (text: string) => void;
}

export function useAutoSendIntent({
  intent,
  ready,
  apiAvailable,
  isTyping,
  isUsageBlocked,
  send,
  fallbackToDraft,
}: UseAutoSendIntentArgs): void {
  const consumedRef = useRef(false);
  useEffect(() => {
    if (!intent || consumedRef.current || !ready) return;
    if (isUsageBlocked) {
      consumedRef.current = true;
      fallbackToDraft(intent);
      return;
    }
    // Not consumable yet — the effect re-runs when these settle.
    if (!apiAvailable || isTyping) return;
    consumedRef.current = true;
    void send(intent);
  }, [intent, ready, apiAvailable, isTyping, isUsageBlocked, send, fallbackToDraft]);
}
