'use client';

/**
 * The five totals the notifications hub badges, in ONE read.
 *
 * Each badge answers the question a reader asks before unfolding a section:
 * *is there anything in there?* Until this hook existed, that total came from
 * the paginated read the fold gated, so the badge said `—` until the section
 * was opened — the one number that decides whether to open a section could
 * only be had by opening it.
 *
 * One request, not five: five separate counts at mount would be the same
 * client-side scatter `useCapabilities` exists to remove. And not zero: "a
 * folded section costs no request" was never about arithmetic but about not
 * paying for ROWS nobody is looking at — the page still waits for the fold.
 */

import { useApplicationAccountQuery } from './useApplicationAccountQuery';
import { useApplicationResourceSync } from './useApplicationResourceSync';

export interface HubCounts {
  peer_messages: number;
  proactive: number;
  interests: number;
  /** Reminders still WAITING — the future, never a history. */
  reminders: number;
  scheduled: number;
  /** Undecided missed-routine offers (Lot 5-C2) — a to-decide set. */
  offers: number;
  /**
   * Tickets that need THIS person (ADR-276): a run stopped waiting for them,
   * or something on their board is overdue. A set to decide, never a count of
   * everything the account owns.
   */
  workboard: number;
  /** Openings LIA started (ADR-358); absence supports older APIs. */
  discussions?: number;
  /** null is a source failure; absence supports older APIs. */
  sms?: number | null;
}

export interface UseHubCountsResult {
  /**
   * The five totals, or `undefined` while they are NOT KNOWN YET.
   *
   * Kept through a failed refresh; an error is never an invented zero.
   */
  counts: HubCounts | undefined;
  error: Error | null;
  loading: boolean;
  refetch: () => Promise<void>;
  /**
   * The account the totals belong to — what a page-wide refresh signals.
   * The totals re-read on the `sms` resource signal, so publishing it IS
   * their refresh: calling `refetch` as well would race a second read.
   */
  ownerId: string | undefined;
}

export function useHubCounts(): UseHubCountsResult {
  const { data, error, loading, refetch, ownerId } = useApplicationAccountQuery<HubCounts>(
    '/notifications/hub-counts',
    'useHubCounts'
  );
  useApplicationResourceSync(ownerId, 'sms', refetch);

  return { counts: data, error, loading, refetch, ownerId };
}
