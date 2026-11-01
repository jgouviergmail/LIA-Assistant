'use client';

/**
 * The « Tools » rail's read of `GET /workbench` (ADR-369): every tool's state,
 * its provider's gestures and bounds, and the limits every route enforces.
 *
 * Read only where the section is offered (the caller passes
 * `workbenchAvailable(config)`), owner-isolated (`useApplicationAccountQuery`),
 * and re-read in place when a connector changes elsewhere — the `connectors`
 * application resource — so a service unlinked in Settings leaves the rail
 * without a reload, and what is on screen stays until the answer lands.
 */
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import type { WorkbenchAvailability } from '@/lib/workbench/types';

export interface WorkbenchAvailabilityState {
  /** The rail, once read for the current account. */
  availability: WorkbenchAvailability | undefined;
  loading: boolean;
  error: unknown;
  refetch: () => Promise<void>;
}

/**
 * @param enabled - Whether the section is offered (nothing is read otherwise).
 * @returns The rail's state.
 */
export function useWorkbenchAvailability(enabled: boolean): WorkbenchAvailabilityState {
  const query = useApplicationAccountQuery<WorkbenchAvailability>(
    '/workbench',
    'useWorkbenchAvailability',
    enabled
  );
  useApplicationResourceSync(enabled ? query.ownerId : undefined, 'connectors', query.refetch);
  return {
    availability: query.data,
    loading: query.loading,
    error: query.error,
    refetch: query.refetch,
  };
}
