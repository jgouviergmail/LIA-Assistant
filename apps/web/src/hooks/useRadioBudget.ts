'use client';

/**
 * useRadioBudget — what the listener's radio spent over the rolling day (ADR-324 decision 37).
 *
 * `GET /radio/budget` publishes the bound the API enforces at every start,
 * before every programme and before every article translation, and what the
 * window holds against it — read once where the settings show it.
 */

import { useApiQuery } from '@/hooks/useApiQuery';
import { RADIO_ENDPOINTS } from '@/lib/radio/api';
import type { RadioBudget } from '@/lib/radio/types';

/**
 * The listener's radio budget.
 *
 * @returns The budget; `null` until it is read, or when it could not be.
 */
export function useRadioBudget(): RadioBudget | null {
  const budget = useApiQuery<RadioBudget>(RADIO_ENDPOINTS.budget, {
    componentName: 'useRadioBudget',
  });
  return budget.data ?? null;
}
