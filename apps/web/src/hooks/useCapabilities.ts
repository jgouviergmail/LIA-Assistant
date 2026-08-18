'use client';

/**
 * What LIA can do for this account — one read, one payload.
 *
 * The starter checklist probes seven capabilities through seven hooks. That is
 * fine for a card the reader dismisses once; for a living map of everything
 * the assistant can do it would mean a dozen requests at mount and a dozen
 * chances for one answer to disagree with another about whether voice is on.
 * The backend resolves them all in one pass instead.
 *
 * The payload holds only what THIS instance offers: a subsystem the deployment
 * disabled is absent, never a greyed-out node (gate-keeper, ADR-061).
 */

import { useApiQuery } from './useApiQuery';

export interface CapabilityNode {
  /** Stable identifier; the label is resolved client-side from it. */
  key: string;
  /** Whether the account can use it right now. */
  active: boolean;
  /**
   * A count the reader can verify (connectors linked, memories kept).
   *
   * Never a score: "3 connectors" is a fact about this account, a percentage
   * of completion is a competition nobody asked to enter.
   */
  detail: number | null;
}

export interface CapabilityMap {
  nodes: CapabilityNode[];
  live: number;
  total: number;
}

export interface UseCapabilitiesOptions {
  /**
   * Whether to read at all. The settings overview is rendered but CSS-hidden
   * below `lg` (the rail is the phone landing), so without this the aggregate
   * would be fetched for a hub nobody on a phone can see — the opposite of the
   * "only what is shown fetches" rule the shell was built on.
   */
  enabled?: boolean;
}

export function useCapabilities({ enabled = true }: UseCapabilitiesOptions = {}) {
  const { data, loading, error, refetch } = useApiQuery<CapabilityMap>('/capabilities', {
    componentName: 'useCapabilities',
    enabled,
  });

  return {
    nodes: data?.nodes,
    live: data?.live ?? 0,
    total: data?.total ?? 0,
    // Derived from `data`, never from `error`: a refetch clears the error, and
    // a spinner keyed on it would blank the map mid-refresh.
    firstLoad: data === undefined && loading,
    loading,
    error,
    refetch,
  };
}
