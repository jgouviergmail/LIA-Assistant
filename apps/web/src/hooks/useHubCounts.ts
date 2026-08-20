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

import { useApiQuery } from './useApiQuery';

export interface HubCounts {
  peer_messages: number;
  proactive: number;
  interests: number;
  /** Reminders still WAITING — the future, never a history. */
  reminders: number;
  scheduled: number;
  /** Undecided missed-routine offers (Lot 5-C2) — a to-decide set. */
  offers: number;
}

export interface UseHubCountsResult {
  /**
   * The five totals, or `undefined` while they are NOT KNOWN YET.
   *
   * Deliberately the only thing exposed. A loading flag and a refetch would
   * both be surface nobody reads: the badge distinguishes "unknown" from a
   * real 0 by the absence of the payload itself, and a section that has been
   * opened shows its own total from then on — the one that follows a
   * deletion. An unused API is a promise the next reader has to check.
   */
  counts: HubCounts | undefined;
}

export function useHubCounts(): UseHubCountsResult {
  const { data } = useApiQuery<HubCounts>('/notifications/hub-counts', {
    componentName: 'useHubCounts',
  });

  return { counts: data };
}
