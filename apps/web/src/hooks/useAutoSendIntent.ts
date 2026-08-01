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
 * Consumed once PER INTENT (StrictMode-proof via ref). "Per intent", not
 * "per mount": production, 2026-08-01 — a 360° recap on one person, then on
 * another, then on a third produced three sends of the SAME sentence. The
 * latch was a plain boolean scoped to the hook instance, so once armed it
 * refused every later request; the second and third deep links executed the
 * first one's text. What re-arms it is a CHANGE of value, which also covers
 * asking twice for the same person: the page clears the param after
 * consumption, so the value passes through '' between two identical requests.
 *
 * While the composer is busy (`isTyping` — e.g. a background run streaming)
 * or the API is not reachable yet, the effect simply retries on the next
 * state change. A usage-blocked session degrades to a persisted draft — the
 * request is saved, never silently dropped, and never force-fed past a wall.
 */

import { useEffect, useRef } from 'react';

import type { CapabilityDirectiveWire } from '@/types/directive';

export interface UseAutoSendIntentArgs {
  /** The decoded `?intent=` value captured at mount ('' = none). */
  intent: string;
  /**
   * The capability the click invoked, when it had one (ADR-191). Travels WITH
   * the intent — the latch stays keyed on the sentence, since the two always
   * arrive and are cleared together.
   *
   * Must be REFERENTIALLY STABLE across renders: it is an effect dependency,
   * so a fresh object literal per render re-runs the effect every render. The
   * latch would still prevent a double send, but a hook that only works
   * because something downstream absorbs the churn is a defect waiting for its
   * next consumer. `useDeepLinkParams` memoizes it on primitives.
   */
  directive?: CapabilityDirectiveWire;
  /** True once auth is resolved (the layout redirects unauthenticated). */
  ready: boolean;
  apiAvailable: boolean;
  isTyping: boolean;
  isUsageBlocked: boolean;
  /** The page's `sendMessageFromPresent`. */
  send: (text: string, directive?: CapabilityDirectiveWire) => void | Promise<unknown>;
  /** Quota-wall fallback: persist as draft + tell the user (no send). */
  fallbackToDraft: (text: string) => void;
  /**
   * Called once the intent has been acted on (sent, or saved as a draft).
   * The page uses it to drop `?intent=` from the URL — which is also what
   * re-arms this hook, so an identical request later still counts as new.
   */
  onConsumed?: () => void;
}

export function useAutoSendIntent({
  intent,
  directive,
  ready,
  apiAvailable,
  isTyping,
  isUsageBlocked,
  send,
  fallbackToDraft,
  onConsumed,
}: UseAutoSendIntentArgs): void {
  // The intent this hook has already acted on — `null` means "armed".
  // Holding the VALUE rather than a boolean is what makes a second, different
  // deep link a second request instead of a silent no-op.
  const consumedRef = useRef<string | null>(null);
  useEffect(() => {
    if (!intent) {
      // The page cleared the param: nothing pending, and the latch is armed
      // again so an IDENTICAL request later still counts as a new one.
      consumedRef.current = null;
      return;
    }
    // A different intent arrived: the previous one is done with, whatever
    // became of it (sent, or saved as a draft behind a quota wall).
    if (consumedRef.current !== null && consumedRef.current !== intent) {
      consumedRef.current = null;
    }
    if (consumedRef.current === intent || !ready) return;
    if (isUsageBlocked) {
      // The draft keeps the SENTENCE, never the directive: a prose draft the
      // user sends later must not smuggle a guaranteed tool call they never
      // re-confirmed. Behind a quota wall the request degrades to what the
      // user can still read and edit.
      consumedRef.current = intent;
      fallbackToDraft(intent);
      onConsumed?.();
      return;
    }
    // Not consumable yet — the effect re-runs when these settle.
    if (!apiAvailable || isTyping) return;
    consumedRef.current = intent;
    void send(intent, directive);
    onConsumed?.();
  }, [
    intent,
    directive,
    ready,
    apiAvailable,
    isTyping,
    isUsageBlocked,
    send,
    fallbackToDraft,
    onConsumed,
  ]);
}
