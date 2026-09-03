'use client';

/**
 * Per-user meeting preferences (ADR-258): engine, language hint, auto-email,
 * audio retention — plus the admin ceiling the retention must respect.
 */

import { useCallback, useEffect, useState } from 'react';

import { useStaleGuard } from '@/hooks/useStaleGuard';
import { logger } from '@/lib/logger';
import { meetingsApi } from '@/lib/meetings/api';
import type { MeetingPreferences, MeetingPreferencesUpdate } from '@/types/meetings';

export interface UseMeetingPreferencesReturn {
  preferences: MeetingPreferences | null;
  isLoading: boolean;
  isSaving: boolean;
  error: Error | null;
  save: (update: MeetingPreferencesUpdate) => Promise<MeetingPreferences | null>;
}

export function useMeetingPreferences(enabled = true): UseMeetingPreferencesReturn {
  const [preferences, setPreferences] = useState<MeetingPreferences | null>(null);
  const [isLoading, setIsLoading] = useState(enabled);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const guard = useStaleGuard();

  useEffect(() => {
    if (!enabled) return;
    const isStale = guard.begin();
    void (async () => {
      try {
        const current = await meetingsApi.preferences();
        if (isStale()) return;
        setPreferences(current);
      } catch (err) {
        if (isStale()) return;
        setError(err instanceof Error ? err : new Error(String(err)));
        logger.error('meeting_preferences_load_failed', err as Error, {
          component: 'useMeetingPreferences',
        });
      } finally {
        if (!isStale()) setIsLoading(false);
      }
    })();
  }, [enabled, guard]);

  const save = useCallback(async (update: MeetingPreferencesUpdate) => {
    setIsSaving(true);
    try {
      const saved = await meetingsApi.putPreferences(update);
      setPreferences(saved);
      setError(null);
      return saved;
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
      return null;
    } finally {
      setIsSaving(false);
    }
  }, []);

  return { preferences, isLoading, isSaving, error, save };
}
