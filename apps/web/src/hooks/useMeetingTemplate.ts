'use client';

/**
 * The user's minutes template (ADR-258).
 *
 * The API answers the built-in default until the user saves one; a reset
 * deletes the saved row and the default comes back in the user's language.
 */

import { useCallback, useEffect, useState } from 'react';

import { useStaleGuard } from '@/hooks/useStaleGuard';
import { logger } from '@/lib/logger';
import { meetingsApi } from '@/lib/meetings/api';
import type { MeetingTemplate, MeetingTemplateUpdate } from '@/types/meetings';

export interface UseMeetingTemplateReturn {
  template: MeetingTemplate | null;
  isLoading: boolean;
  isSaving: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
  save: (update: MeetingTemplateUpdate) => Promise<MeetingTemplate | null>;
  reset: () => Promise<MeetingTemplate | null>;
}

export function useMeetingTemplate(enabled = true): UseMeetingTemplateReturn {
  const [template, setTemplate] = useState<MeetingTemplate | null>(null);
  const [isLoading, setIsLoading] = useState(enabled);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const guard = useStaleGuard();

  const refetch = useCallback(async () => {
    if (!enabled) return;
    const isStale = guard.begin();
    try {
      const current = await meetingsApi.template();
      if (isStale()) return;
      setTemplate(current);
      setError(null);
    } catch (err) {
      if (isStale()) return;
      setError(err instanceof Error ? err : new Error(String(err)));
      logger.error('meeting_template_load_failed', err as Error, {
        component: 'useMeetingTemplate',
      });
    } finally {
      if (!isStale()) setIsLoading(false);
    }
  }, [enabled, guard]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  const save = useCallback(async (update: MeetingTemplateUpdate) => {
    setIsSaving(true);
    try {
      const saved = await meetingsApi.putTemplate(update);
      setTemplate(saved);
      return saved;
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
      return null;
    } finally {
      setIsSaving(false);
    }
  }, []);

  const reset = useCallback(async () => {
    setIsSaving(true);
    try {
      const restored = await meetingsApi.resetTemplate();
      setTemplate(restored);
      return restored;
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
      return null;
    } finally {
      setIsSaving(false);
    }
  }, []);

  return { template, isLoading, isSaving, error, refetch, save, reset };
}
