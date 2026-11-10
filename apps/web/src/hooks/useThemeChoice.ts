'use client';

import { useCallback, useState } from 'react';
import {
  readThemeSchedule,
  type StoredThemeSchedule,
  type ThemeSchedule,
} from '@/lib/theme-schedule';

type Hours = Pick<ThemeSchedule, 'lightStartMinute' | 'darkStartMinute'>;
interface AccountChoice extends ThemeSchedule {
  ownerId: string | undefined;
  mode: string | undefined;
}

/** Reconcile account snapshots during render, preserving a pending local choice. */
export function useThemeChoice(account: AccountChoice, loading: boolean, pending: boolean) {
  const sourceKey = JSON.stringify(account);
  const [choice, setChoice] = useState(() => ({
    sourceKey: '',
    ownerId: account.ownerId,
    saveError: false,
    automatic: readThemeSchedule(),
    hours: { lightStartMinute: account.lightStartMinute, darkStartMinute: account.darkStartMinute },
  }));
  if (!loading && sourceKey !== choice.sourceKey) {
    const sameOwner = choice.ownerId === account.ownerId;
    const retainLocal = sameOwner && (pending || choice.saveError);
    const automatic =
      account.mode === 'auto' && account.ownerId
        ? {
            ownerId: account.ownerId,
            timezone: account.timezone,
            lightStartMinute: account.lightStartMinute,
            darkStartMinute: account.darkStartMinute,
          }
        : null;
    setChoice({
      sourceKey,
      ownerId: account.ownerId,
      saveError: sameOwner && choice.saveError,
      automatic: retainLocal ? choice.automatic : automatic,
      hours: retainLocal
        ? choice.hours
        : { lightStartMinute: account.lightStartMinute, darkStartMinute: account.darkStartMinute },
    });
  }
  const setAutomatic = useCallback((automatic: StoredThemeSchedule | null) => {
    setChoice(current => ({ ...current, automatic }));
  }, []);
  const setHours = useCallback((hours: Hours) => setChoice(current => ({ ...current, hours })), []);
  const setSaveError = useCallback(
    (saveError: boolean) => setChoice(current => ({ ...current, saveError })),
    []
  );
  return {
    automatic: choice.automatic,
    hours: choice.hours,
    saveError: choice.saveError,
    setAutomatic,
    setHours,
    setSaveError,
  };
}
