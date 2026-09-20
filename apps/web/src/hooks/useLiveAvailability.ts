'use client';

/**
 * Whether the live mode is offered to this account (ADR-299), and on which
 * provider its sessions open (ADR-300, the `live` category is additive): the
 * instance publishes the capability AND the account holds an active live
 * connector. One reading for the header menu and the settings; the connectors
 * are read once per mount, only when the capability is on — and again each
 * time the Live settings declare them changed (`live_connectors` revision):
 * the header sits in the dashboard layout and never remounts on the way
 * back from the settings (owner request 2026-09-19).
 */
import { useApiQuery } from '@/hooks/useApiQuery';
import { useAppConfig } from '@/hooks/useAppConfig';
import type { LiveConnectorsResponse } from '@/lib/live/types';
import { useResourceRevision } from '@/stores/revisionStore';

export interface LiveAvailability {
  available: boolean;
  /** The provider id the sessions open on — `null` while none is available. */
  provider: string | null;
  /**
   * The chosen model's wire carries a tool schema, so a DIRECT session can
   * be offered (ADR-300 wave 4); a capability of the model, never a provider id.
   */
  directTools: boolean;
}

export function useLiveAvailability(): LiveAvailability {
  const { config } = useAppConfig();
  const liveEnabled = !!config?.features?.live_enabled;
  const revision = useResourceRevision('live_connectors');
  const { data } = useApiQuery<LiveConnectorsResponse>('/live/connectors', {
    componentName: 'useLiveAvailability',
    enabled: liveEnabled,
    deps: [revision],
  });
  const connectors = data?.connectors ?? [];
  const available = liveEnabled && connectors.some(c => c.status === 'active');
  const provider = available ? (data?.active_provider ?? null) : null;
  const chosen = connectors.find(c => c.provider === provider && c.status === 'active');
  return { available, provider, directTools: chosen?.capabilities.direct_tools === true };
}
