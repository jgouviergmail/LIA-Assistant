'use client';

/**
 * useWorkboardSummary — the board at a glance (ADR-276, lot 18).
 *
 * One read, `GET /workboard/summary`: every figure an aggregate over the whole
 * board (ADR-185) and the caps the instance enforces (ADR-184), for the
 * settings section that shows them. `enabled` follows the instance flag so a
 * section that renders nothing asks for nothing.
 */

import { useApiQuery } from '@/hooks/useApiQuery';
import type { BoardSummary } from '@/types/workboard';

export interface UseWorkboardSummaryReturn {
  /** The figures, or `undefined` while they are not known yet — or refused. */
  summary: BoardSummary | undefined;
  loading: boolean;
  error: boolean;
}

export function useWorkboardSummary(enabled = true): UseWorkboardSummaryReturn {
  const { data, loading, error } = useApiQuery<BoardSummary>('/workboard/summary', {
    componentName: 'useWorkboardSummary',
    enabled,
  });
  return { summary: data, loading, error: !!error };
}
