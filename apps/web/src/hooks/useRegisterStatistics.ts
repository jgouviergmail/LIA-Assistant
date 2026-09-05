'use client';

/**
 * useRegisterStatistics — the five records as figures (ADR-263).
 *
 * One hook for both audiences, because the question is the same and only the
 * scope differs: a reader asks about themselves, an operator about one, several
 * or every account. Two hooks would be two places for a chart to be right on
 * one screen and wrong on the other.
 *
 * Nothing is computed here. Every count arrives already aggregated — a client
 * that fetched rows to count them would download the very content the registers
 * exist to keep in one place, and would get a different answer than the export.
 */

import { useMemo } from 'react';

import { useApiQuery } from '@/hooks/useApiQuery';

/** One bar: a BOUNDED label and its exact count. */
export interface StatisticsSlice {
  label: string;
  count: number;
  /** A second measure on the same bar (completion tokens beside prompt ones). */
  secondary: number;
}

/**
 * What the bars of a series draw — and therefore what its badge may claim.
 *
 * A sum of means is not a quantity, and a badge counting one measure of a
 * STACKED bar is shorter than the bar it sits beside. Both were shipped before
 * the server said which kind it was sending.
 */
export type SeriesKind = 'count' | 'stacked' | 'average';

/** One chart, with the exact figure for the whole filtered set beside it. */
export interface StatisticsSeries {
  slices: StatisticsSlice[];
  /**
   * The EXACT figure for the whole filtered set, including whatever the
   * server's top-N folded into « other » (ADR-185). A SUM for `count` and
   * `stacked`, a weighted MEAN for `average` — read `kind` before showing it.
   */
  total: number;
  kind: SeriesKind;
}

/** Every series the surfaces draw. */
export interface RegisterStatistics {
  calls_by_model: StatisticsSeries;
  calls_by_node: StatisticsSeries;
  tokens_by_model: StatisticsSeries;
  consultations_by_domain: StatisticsSeries;
  consultation_latency_by_tool: StatisticsSeries;
  actions_by_status: StatisticsSeries;
  turns_by_outcome: StatisticsSeries;
  turns_by_mode: StatisticsSeries;
  integrity_by_kind: StatisticsSeries;
  activity_by_day: StatisticsSeries;
}

export interface UseRegisterStatisticsOptions {
  /**
   * Accounts to cover. Omitted means the caller's own — and the reader's route
   * takes no account parameter at all, so their scope is their session and
   * there is nothing to pass.
   */
  userIds?: string[];
  /** Read the administrator's cross-account endpoint instead of one's own. */
  admin?: boolean;
  since?: string;
  until?: string;
}

export interface UseRegisterStatisticsResult {
  statistics: RegisterStatistics | undefined;
  loading: boolean;
  error: Error | null;
  refetch: () => void;
}

/**
 * Read the registers as figures.
 *
 * @param options - Scope and period. An empty account list on the
 *   administrator's endpoint means the whole instance, deliberately.
 */
export function useRegisterStatistics(
  options: UseRegisterStatisticsOptions = {}
): UseRegisterStatisticsResult {
  const { userIds, admin = false, since, until } = options;

  const path = useMemo(() => {
    const params = new URLSearchParams();
    if (admin) for (const id of userIds ?? []) params.append('user_ids', id);
    if (since) params.set('since', since);
    if (until) params.set('until', until);
    const query = params.toString();
    const base = admin ? '/admin/effects/statistics' : '/effects/statistics';
    return query ? `${base}?${query}` : base;
  }, [admin, userIds, since, until]);

  const { data, loading, error, refetch } = useApiQuery<RegisterStatistics>(path, {
    componentName: 'useRegisterStatistics',
    deps: [path],
  });

  return { statistics: data ?? undefined, loading, error, refetch };
}
