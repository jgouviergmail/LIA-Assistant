/** Account-bound connector preferences, serialized writes and verified native rereads. */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { toast } from 'sonner';
import { z } from '@/lib/zod';
import apiClient from '@/lib/api-client';
import { getApiErrorDetail } from '@/lib/api-error';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import { CONNECTORS_WITH_PREFERENCES, PREFERENCE_FIELDS } from '../constants';
import type { Connector, ConnectorPreferences } from '../types';

interface UseConnectorPreferencesOptions { connectors: Connector[]; t: (key: string) => string }

const preferenceValues = z.object({
  default_calendar_name: z.string().nullable().optional(),
  default_task_list_name: z.string().nullable().optional(),
}).strict();

async function readSaved(connectorId: string): Promise<ConnectorPreferences> {
  const response = await apiClient.get<{ preferences: unknown }>(`/connectors/${connectorId}/preferences`);
  return preferenceValues.parse(response.preferences);
}

function canRead(
  phase: { loaded: ReadonlySet<string>; loading: ReadonlySet<string> },
  connectorId: string, force: boolean, current: boolean,
) {
  return current && (force || (!phase.loaded.has(connectorId) && !phase.loading.has(connectorId)));
}

async function drainWrites(queues: ReadonlyMap<string, Promise<void>>, connectorId: string) {
  let pending = queues.get(connectorId);
  while (pending) {
    await pending;
    const next = queues.get(connectorId);
    if (next === pending) return;
    pending = next;
  }
}

export function useConnectorPreferences({ connectors, t }: UseConnectorPreferencesOptions) {
  const { user } = useAuth();
  const { lifetime, isCurrent } = useApplicationAccountLifetime(user?.id);
  const phase = useMemo(() => ({
    lifetime,
    loaded: new Set<string>(), loading: new Set<string>(), local: new Set<string>(),
    sequences: new Map<string, number>(), revisions: new Map<string, number>(),
    queues: new Map<string, Promise<void>>(), confirmed: new Map<string, ConnectorPreferences>(),
  }), [lifetime]);
  const [state, setState] = useState<{ lifetime: typeof lifetime; prefs: Record<string, ConnectorPreferences> } | null>(null);
  const [saving, setSaving] = useState<{ lifetime: typeof lifetime; id: string; revision: number } | null>(null);
  const savedPrefs = state?.lifetime === lifetime ? state.prefs : {};

  const load = useCallback(async (connectorId: string, force: boolean, expectedRevision?: number) => {
    if (!canRead(phase, connectorId, force, isCurrent())) return;
    phase.loading.add(connectorId);
    const sequence = (phase.sequences.get(connectorId) ?? 0) + 1;
    phase.sequences.set(connectorId, sequence);
    const revision = expectedRevision ?? phase.revisions.get(connectorId);
    try {
      const prefs = await readSaved(connectorId);
      if (!isCurrent() || phase.sequences.get(connectorId) !== sequence) return;
      if (!force && phase.local.has(connectorId)) return;
      phase.confirmed.set(connectorId, prefs);
      if (force && revision !== phase.revisions.get(connectorId)) return;
      if (force) phase.local.delete(connectorId);
      setState(current => ({ lifetime, prefs: {
        ...(current?.lifetime === lifetime ? current.prefs : {}), [connectorId]: prefs,
      } }));
    } catch (error: unknown) {
      if (force && isCurrent()) throw error;
    } finally {
      phase.loading.delete(connectorId);
      phase.loaded.add(connectorId);
    }
  }, [isCurrent, lifetime, phase]);

  const supported = useMemo(() => connectors.filter(connector =>
    CONNECTORS_WITH_PREFERENCES.includes(connector.connector_type)), [connectors]);
  useEffect(() => { supported.forEach(connector => { void load(connector.id, false); }); }, [supported, load]);
  const refetch = useCallback(async () => {
    await Promise.all(supported.map(async connector => {
      await drainWrites(phase.queues, connector.id);
      await load(connector.id, true);
    }));
  }, [supported, phase, load]);
  const release = useCallback(() => {}, []);
  useApplicationResourceSync(user?.id, 'connector_preferences', refetch, release);

  const selectPreference = useCallback(async (connectorId: string, connectorType: string, value: string) => {
    const field = PREFERENCE_FIELDS[connectorType];
    if (!field || !isCurrent() || !supported.some(connector => connector.id === connectorId && connector.connector_type === connectorType)) return;
    const revision = (phase.revisions.get(connectorId) ?? 0) + 1;
    phase.revisions.set(connectorId, revision);
    phase.local.add(connectorId);
    setSaving({ lifetime, id: connectorId, revision });
    setState(current => ({ lifetime, prefs: {
      ...(current?.lifetime === lifetime ? current.prefs : {}),
      [connectorId]: { ...(current?.lifetime === lifetime ? current.prefs[connectorId] : {}), [field]: value },
    } }));
    const queued = phase.queues.get(connectorId) ?? Promise.resolve();
    const writing = queued.then(async () => {
      if (!isCurrent()) return;
      try {
        await apiClient.patch(`/connectors/${connectorId}/preferences`, { [field]: value });
      } catch (error: unknown) {
        if (!isCurrent()) return;
        if (phase.revisions.get(connectorId) === revision) {
          phase.local.delete(connectorId);
          setState(current => current?.lifetime !== lifetime ? current : {
            lifetime, prefs: { ...current.prefs, [connectorId]: phase.confirmed.get(connectorId) ?? {} },
          });
        }
        toast.error(getApiErrorDetail(error) ?? t('settings.connectors.preferences.error'));
        return;
      }
      if (!isCurrent()) return;
      try { await load(connectorId, true, revision); }
      catch { if (isCurrent()) toast.error(t('settings.application_tools.sync_failed')); }
      if (isCurrent()) toast.success(t(value ? 'settings.connectors.preferences.saved' : 'settings.connectors.preferences.cleared'));
    });
    phase.queues.set(connectorId, writing);
    try { await writing; }
    finally {
      if (phase.queues.get(connectorId) === writing) phase.queues.delete(connectorId);
      setSaving(current => current?.lifetime === lifetime && current.id === connectorId && current.revision === revision ? null : current);
    }
  }, [supported, phase, isCurrent, lifetime, load, t]);

  return { savedPrefs, savingPreference: saving?.lifetime === lifetime ? saving.id : null, selectPreference };
}
