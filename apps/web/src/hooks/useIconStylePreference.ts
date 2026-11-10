'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useApiMutation } from '@/hooks/useApiMutation';
import type { User } from '@/lib/auth';
import { DEFAULT_ICON_STYLE, type IconStyle, type IconStyleUpdate } from '@/lib/icon-style';

export interface IconStylePreference {
  style: IconStyle;
  saving: boolean;
  failed: boolean;
  selectStyle: (style: IconStyle) => void;
  retry: () => void;
}

/** Mounted once per account; switching accounts cancels its queue and request. */
export function useIconStylePreference(
  user: User | null,
  applyUserUpdate: (updated: IconStyleUpdate) => boolean
): IconStylePreference {
  const accountStyle = user?.icon_style ?? DEFAULT_ICON_STYLE;
  const [choice, setChoice] = useState<IconStyle | null>(null);
  const [saving, setSaving] = useState(false);
  const [failedChoice, setFailedChoice] = useState<IconStyle | null>(null);
  const pending = useRef<IconStyle | null>(null);
  const active = useRef<AbortController | null>(null);
  const { mutate } = useApiMutation<{ icon_style: IconStyle }, User>({
    method: 'PATCH',
    componentName: 'useIconStylePreference',
    retainResponse: false,
  });

  useEffect(
    () => () => {
      pending.current = null;
      active.current?.abort();
      active.current = null;
    },
    []
  );

  const selectStyle = useCallback(
    (next: IconStyle) => {
      if (!user) return;
      setChoice(next);
      setFailedChoice(null);
      pending.current = next;
      if (active.current) return;

      const controller = new AbortController();
      active.current = controller;
      setSaving(true);
      const drain = async () => {
        try {
          while (pending.current !== null && !controller.signal.aborted) {
            const value = pending.current;
            pending.current = null;
            try {
              const result = await mutate(
                `/users/${user.id}`,
                { icon_style: value },
                {
                  signal: controller.signal,
                }
              );
              if (controller.signal.aborted) return;
              if (result?.icon_style !== value || result.id !== user.id)
                throw new Error('Icon preference was not confirmed');
              // Publish only the field this mutation owns. Other preferences
              // may have changed while this PATCH response was in flight.
              if (!applyUserUpdate({ id: result.id, icon_style: value }))
                throw new Error('Account changed during icon update');
              if (pending.current === null) {
                setChoice(null);
              }
            } catch {
              if (controller.signal.aborted) return;
              if (pending.current === null) {
                setChoice(null);
                setFailedChoice(value);
              }
            }
          }
        } finally {
          if (!controller.signal.aborted) {
            active.current = null;
            setSaving(false);
          }
        }
      };
      void drain();
    },
    [user, mutate, applyUserUpdate]
  );

  return {
    style: choice ?? accountStyle,
    saving,
    failed: failedChoice !== null,
    selectStyle,
    retry: () => {
      if (failedChoice !== null) selectStyle(failedChoice);
    },
  };
}
