'use client';

import { useCallback, useLayoutEffect, useRef } from 'react';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import type { ApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { publishApplicationResources } from '@/lib/application-resources';
import { smsPreferencesSchema, type SmsPreferences, type SmsSettings } from '@/types/sms';

/** A settings click saves one field; source invalidation also reconciles lost acknowledgements. */
export function useSmsPreferenceUpdate(
  query: ReturnType<typeof useApplicationAccountQuery<SmsSettings>>
) {
  const { ownerId, lifetime, isCurrent, acceptData } = query;
  const latestData = useRef(query.data);
  useLayoutEffect(() => {
    latestData.current = query.data;
  }, [query.data]);
  const inFlight = useRef<ApplicationAccountLifetime | null>(null);
  const [saving, setSaving] = useApplicationAccountState(ownerId, false);
  const [error, setError] = useApplicationAccountState(ownerId, false);
  const { mutate } = useApiMutation<{ field: keyof SmsPreferences; value: boolean }, unknown>({
    method: 'PATCH',
    componentName: 'useSmsPreferenceUpdate',
    retainResponse: false,
  });
  const updatePreference = useCallback(
    async (field: keyof SmsPreferences, value: boolean) => {
      if (!isCurrent() || inFlight.current === lifetime) return;
      inFlight.current = lifetime;
      setSaving(true);
      setError(false);
      try {
        const preferences = smsPreferencesSchema.parse(
          await mutate('/sms/preferences', { field, value })
        );
        if (isCurrent() && latestData.current) acceptData({ ...latestData.current, preferences });
      } catch {
        if (isCurrent()) setError(true);
      } finally {
        if (inFlight.current === lifetime) inFlight.current = null;
        setSaving(false);
        if (isCurrent() && ownerId) publishApplicationResources(ownerId, new Set(['sms']));
      }
    },
    [isCurrent, lifetime, setSaving, setError, mutate, acceptData, ownerId]
  );
  return { updatePreference, saving, error };
}
