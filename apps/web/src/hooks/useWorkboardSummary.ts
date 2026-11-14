'use client';

/**
 * useWorkboardSummary — the board at a glance (ADR-276, lot 18).
 *
 * One read, `GET /workboard/summary`: every figure an aggregate over the whole
 * board (ADR-185) and the caps the instance enforces (ADR-184), for the block
 * that shows them above the board's filters. `enabled` lets a block that shows
 * nothing ask for nothing, and `stamp` is how the board says its figures may
 * have moved: the read is taken again whenever it changes, and what is on
 * screen stays there until the answer lands.
 */

import { useApiQuery } from '@/hooks/useApiQuery';
import type { BoardSummary } from '@/types/workboard';

export interface UseWorkboardSummaryReturn {
  /** The figures, or `undefined` while they are not known yet — or refused. */
  summary: BoardSummary | undefined;
  loading: boolean;
  error: boolean;
}

/**
 * @param enabled - Whether to read at all.
 * @param stamp - Changes whenever the figures may have moved.
 * @returns The figures and the state of their read.
 */
export function useWorkboardSummary(enabled = true, stamp = ''): UseWorkboardSummaryReturn {
  const { data, loading, error } = useApiQuery<BoardSummary>('/workboard/summary', {
    componentName: 'useWorkboardSummary',
    enabled,
    deps: [stamp],
  });
  return { summary: data, loading, error: !!error };
}
