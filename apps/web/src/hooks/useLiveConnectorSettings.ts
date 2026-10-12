'use client';

/**
 * The live connectors as the settings show them (ADR-299, spec A10; wave 2
 * A10): every active connector with the one the sessions open on, the union
 * of the models their keys discover today (each naming its provider), the
 * voices of the provider under edit — the active one until the person picks
 * another provider's model — and one door to change model, voice and thinking
 * level, per provider: the provider judges the pair again on every save, its
 * refusal comes back in its own words (`detail.message`), and the connector
 * saved becomes the one the sessions open on — declared to every reader of
 * the live connectors elsewhere (the header's voice menu) through the
 * `live_connectors` revision.
 *
 * The reads run only once a connector exists: without one the section shows
 * a link to the connectors, not three empty lists. A voice listing is handed
 * over only when it names the provider asked for — the query hook renders one
 * stale frame on a key change, and a save in that frame would pair one
 * provider's model with another's voice.
 */
import { useCallback, useRef } from 'react';

import { getApiErrorDetail } from '@/lib/api-error';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import type {
  LiveConfigResponse,
  LiveConnectorResponse,
  LiveConnectorSettings,
  LiveConnectorsResponse,
  LiveModelsResponse,
  LiveVoicesResponse,
} from '@/lib/live/types';
import { bumpRevision } from '@/stores/revisionStore';

export interface UseLiveConnectorSettingsReturn {
  /** `undefined` until the answer lands; an empty list when the account has none. */
  connectors: LiveConnectorsResponse | undefined;
  models: LiveModelsResponse | undefined;
  /** The voices of the provider under edit; `undefined` while they load. */
  voices: LiveVoicesResponse | undefined;
  /** The published bounds and defaults of the per-model durations. */
  config: LiveConfigResponse | undefined;
  /** The connectors and the models — the voices load on their own, inside the form. */
  loading: boolean;
  saving: boolean;
  /** The provider's or the API's sentence for the last refused save. */
  saveError: string | null;
  save: (provider: string, settings: LiveConnectorSettings) => Promise<boolean>;
}

/** The connector the form starts from: the one the sessions open on, else the first. */
export function activeLiveConnector(
  connectors: LiveConnectorsResponse | undefined
): LiveConnectorResponse | undefined {
  return connectors?.connectors.find(c => c.active) ?? connectors?.connectors[0];
}

export function useLiveConnectorSettings(
  enabled = true,
  editedProvider: string | null = null
): UseLiveConnectorSettingsReturn {
  const connectorsQuery = useApplicationAccountQuery<LiveConnectorsResponse>(
    '/live/connectors',
    'useLiveConnectorSettings',
    enabled
  );
  const { ownerId, refetch } = connectorsQuery;
  const { lifetime, isCurrent } = useApplicationAccountLifetime(ownerId);
  const queues = useRef(new Map<typeof lifetime, Promise<boolean>>());
  const release = useCallback(() => {}, []);
  useApplicationResourceSync(ownerId, 'live_connectors', refetch, release);
  const hasConnector = enabled && (connectorsQuery.data?.connectors.length ?? 0) > 0;
  const configQuery = useApplicationAccountQuery<LiveConfigResponse>(
    '/live/config',
    'useLiveConnectorSettings',
    hasConnector
  );
  const modelsQuery = useApplicationAccountQuery<LiveModelsResponse>(
    '/live/models',
    'useLiveConnectorSettings',
    hasConnector
  );
  const voicesProvider = editedProvider ?? activeLiveConnector(connectorsQuery.data)?.provider;
  const voicesQuery = useApplicationAccountQuery<LiveVoicesResponse>(
    `/live/voices?provider=${encodeURIComponent(voicesProvider ?? '')}`,
    'useLiveConnectorSettings',
    hasConnector && !!voicesProvider
  );
  const { mutate } = useApiMutation<LiveConnectorSettings, LiveConnectorResponse>({
    method: 'PUT',
    componentName: 'useLiveConnectorSettings',
  });
  const [saveError, setSaveError] = useApplicationAccountState<string | null>(ownerId, null);
  const [saving, setSaving] = useApplicationAccountState(ownerId, false);
  const { setData: setConnectors } = connectorsQuery;

  const write = useCallback(
    async (provider: string, settings: LiveConnectorSettings): Promise<boolean> => {
      if (!isCurrent()) return false;
      setSaveError(null);
      setSaving(true);
      try {
        const saved = await mutate(`/live/connectors/${encodeURIComponent(provider)}`, settings);
        if (!isCurrent() || !saved) return false;
        {
          // The saved connector is now the one the sessions open on.
          setConnectors(current =>
            current
              ? {
                  active_provider: saved.provider,
                  connectors: current.connectors.map(c =>
                    c.provider === saved.provider ? saved : { ...c, active: false }
                  ),
                }
              : current
          );
          bumpRevision('live_connectors');
        }
        return true;
      } catch (error) {
        if (isCurrent())
          setSaveError(getApiErrorDetail(error) ?? (error instanceof Error ? error.message : ''));
        return false;
      }
    },
    [mutate, setConnectors, isCurrent, setSaveError, setSaving]
  );

  const save = useCallback(
    async (provider: string, settings: LiveConnectorSettings) => {
      if (!isCurrent()) return false;
      setSaving(true);
      const pending = queues.current.get(lifetime) ?? Promise.resolve(false);
      const writing = pending.then(() => write(provider, settings));
      queues.current.set(lifetime, writing);
      try {
        return await writing;
      } finally {
        if (queues.current.get(lifetime) === writing) {
          queues.current.delete(lifetime);
          if (isCurrent()) setSaving(false);
        }
      }
    },
    [isCurrent, lifetime, write, setSaving]
  );

  const voices = voicesQuery.data;
  return {
    connectors: connectorsQuery.data,
    models: modelsQuery.data,
    voices: voices && voices.provider === voicesProvider ? voices : undefined,
    config: configQuery.data,
    loading:
      connectorsQuery.loading || (hasConnector && (modelsQuery.loading || configQuery.loading)),
    saving,
    saveError,
    save,
  };
}
