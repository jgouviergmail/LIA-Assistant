'use client';

import { useApiQuery } from './useApiQuery';

/**
 * What the assistant achieved for this account over the billing cycle.
 *
 * Four exact aggregates. Two candidates are deliberately absent rather than
 * estimated: "time saved", which nothing in this system measures, and
 * "documents actually used", which no table records durably — an injected
 * chunk is not a used one.
 */
export interface PersonalResults {
  /** Start of the window these cover — the same cycle the consumption uses. */
  cycle_start: string;
  /** Results the reader (or the validation window) confirmed useful. */
  useful_results: number;
  /** Successful actions among them. */
  actions: number;
  /** Successful routine runs among them. */
  automations: number;
  /** Commitments closed during the window. */
  commitments_closed: number;
  /**
   * Whether outcome recording is enabled on this instance.
   *
   * False must never be rendered as four zeros: "you achieved nothing" and
   * "nothing is being measured" are different statements, and only one of them
   * would be true.
   */
  measured: boolean;
}

/** Results achieved this cycle, or undefined while the first load runs. */
export function usePersonalResults() {
  const { data, loading, error } = useApiQuery<PersonalResults>('/product/me/results', {
    componentName: 'usePersonalResults',
  });

  return {
    results: data,
    // Monotone: derived from the absence of data, never from `error` (which a
    // refetch clears and which would unmount the block mid-refresh).
    firstLoad: data === undefined && loading,
    error,
  };
}
