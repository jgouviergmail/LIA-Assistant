'use client';

/**
 * Per-user meeting preferences (ADR-258): engine, language hint, auto-email,
 * audio retention — plus the admin ceiling the retention must respect.
 */

import { useCallback, useRef } from 'react';

import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import { MEETING_PREFERENCES_PATH, meetingsApi } from '@/lib/meetings/api';
import type { MeetingPreferences, MeetingPreferencesUpdate } from '@/types/meetings';

export interface UseMeetingPreferencesReturn {
  preferences: MeetingPreferences | null;
  isLoading: boolean;
  isSaving: boolean;
  error: Error | null;
  save: (update: MeetingPreferencesUpdate) => Promise<MeetingPreferences | null>;
}

export function useMeetingPreferences(enabled = true): UseMeetingPreferencesReturn {
  const query = useApplicationAccountQuery<MeetingPreferences>(
    MEETING_PREFERENCES_PATH,
    'useMeetingPreferences',
    enabled
  );
  const { ownerId, lifetime, isCurrent, setData, refetch } = query;
  const [isSaving, setIsSaving] = useApplicationAccountState(ownerId, false);
  const [saveError, setSaveError] = useApplicationAccountState<Error | null>(ownerId, null);
  const pending = useRef<typeof lifetime | null>(null);
  useApplicationResourceSync(enabled ? ownerId : undefined, 'meeting_preferences', refetch);

  const save = useCallback(
    async (update: MeetingPreferencesUpdate) => {
      if (!enabled || !isCurrent() || pending.current === lifetime) return null;
      pending.current = lifetime;
      setIsSaving(true);
      try {
        const saved = await meetingsApi.putPreferences(update);
        if (!isCurrent()) return null;
        setData(saved);
        setSaveError(null);
        return saved;
      } catch (err) {
        if (isCurrent()) setSaveError(err instanceof Error ? err : new Error(String(err)));
        return null;
      } finally {
        if (pending.current === lifetime) pending.current = null;
        if (isCurrent()) setIsSaving(false);
      }
    },
    [enabled, isCurrent, lifetime, setData, setSaveError, setIsSaving]
  );

  return {
    preferences: enabled ? (query.data ?? null) : null,
    isLoading: query.loading,
    isSaving,
    error: saveError ?? query.error ?? null,
    save,
  };
}
