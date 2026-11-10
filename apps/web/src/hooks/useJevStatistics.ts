'use client';

import { useApiQuery, type UseApiQueryResult } from '@/hooks/useApiQuery';
import type { JevStatisticsResponse } from '@/types/jev';

export const JEV_STATISTICS_ENDPOINT = '/admin/llm-config/jev/statistics';
/** The window the screen reads and states, in whole UTC days (the server allows 1–90). */
export const JEV_STATISTICS_WINDOW_DAYS = 30;

/**
 * JEV's durable statistics over the screen's window (ADR-374), administrators only.
 *
 * Read once with the section: the share a threshold concludes is then computed on the
 * screen from the buckets, so moving a slider asks the server nothing.
 */
export function useJevStatistics(): UseApiQueryResult<JevStatisticsResponse> {
  return useApiQuery<JevStatisticsResponse>(
    `${JEV_STATISTICS_ENDPOINT}?days=${JEV_STATISTICS_WINDOW_DAYS}`,
    { componentName: 'AdminJevSection' }
  );
}
