'use client';

/**
 * useHabits — the learned-habits control surface (ADR-214).
 *
 * Everything the rhythm/recurrence detectors learned, user-controllable end
 * to end: consult (profile + rows), pause/resume, block (never relearn),
 * delete one, forget everything, and the learning master toggle. The router
 * is mounted only when HABITS_ENABLED — a 404 marks the surface
 * `unavailable` (the section renders nothing; belt-and-braces beside the
 * /config flag gate, same doctrine as useOpenLoops).
 */

import { useCallback } from 'react';

import { ApiError } from '@/lib/api-client';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';

export type HabitVerdict = 'windows' | 'diffuse' | 'none' | 'insufficient' | 'sparse';
export type HabitStatus = 'active' | 'paused' | 'blocked';
export type HabitKind = 'active_window' | 'recurring_request';

export interface HabitWindow {
  start_hour: number;
  /** Exclusive end hour — may wrap past midnight. */
  end_hour: number;
  presence: number;
}

export interface HabitsProfileClass {
  verdict: HabitVerdict;
  windows: HabitWindow[];
  n_eff: number;
  /** Effective days required before claims — published so the unlock is quantified. */
  required_n_eff: number;
  /** The presence a window must REALLY reach for this class — published
   *  because it is enforced (ADR-184; Wilson floor dominates at low n_eff). */
  effective_presence_min: number;
  /** Weighted per-hour day-presence, 24 values — heatmap source, present for every verdict. */
  bin_presence: number[];
}

export interface HabitsProfile {
  computed_at: string | null;
  weekday: HabitsProfileClass;
  weekend: HabitsProfileClass;
  active_days_fraction: number;
  sparse: boolean;
}

export interface Habit {
  id: string;
  kind: HabitKind;
  key: string;
  payload: Record<string, unknown>;
  status: HabitStatus;
  positive_signals: number;
  negative_signals: number;
  last_observed_at: string;
  created_at: string;
}

export interface HabitCandidate {
  /** Domain signature, e.g. "email+contact". */
  key: string;
  /** Distinct local days observed inside the recurrence window. */
  observed_days: number;
  /** Enforced existence threshold — published by the backend (ADR-184). */
  required_days: number;
}

export interface HabitsOverview {
  habits_enabled: boolean;
  profile: HabitsProfile;
  habits: Habit[];
  /** Recurrence signatures under observation (capped server-side). */
  candidates: HabitCandidate[];
  /** Candidates beyond the display cap — a cap is stated, never silent. */
  candidates_more: number;
}

/** "08:00–10:00" — the wrap-aware window label (locale-independent digits). */
export function formatWindow(window: HabitWindow): string {
  const pad = (h: number) => `${String(h).padStart(2, '0')}:00`;
  return `${pad(window.start_hour)}–${pad(window.end_hour)}`;
}

export interface UseHabitsReturn {
  overview: HabitsOverview | null;
  loading: boolean;
  /** Surface absent on this instance (router unmounted, 404) — render nothing. */
  unavailable: boolean;
  /** Transient listing failure (network, 5xx) — offer a retry, not silence. */
  loadError: boolean;
  refetch: () => void;
  setStatus: (id: string, status: HabitStatus) => Promise<boolean>;
  remove: (id: string) => Promise<boolean>;
  removeAll: () => Promise<boolean>;
  setEnabled: (enabled: boolean) => Promise<boolean>;
  /** Run the nightly unit of work NOW (retroactive over existing history). */
  recompute: () => Promise<boolean>;
}

export function useHabits(enabled = true): UseHabitsReturn {
  const { data, loading, error, refetch } = useApiQuery<HabitsOverview>('/habits', {
    componentName: 'useHabits',
    enabled,
  });

  const { mutate: postStatus } = useApiMutation<{ status: HabitStatus }, Habit>({
    method: 'POST',
    componentName: 'useHabits',
  });
  const { mutate: deleteOne } = useApiMutation<undefined, undefined>({
    method: 'DELETE',
    componentName: 'useHabits',
  });
  const { mutate: patchSettings } = useApiMutation<
    { habits_enabled: boolean },
    { habits_enabled: boolean }
  >({
    method: 'PATCH',
    componentName: 'useHabits',
  });
  const { mutate: postRecompute } = useApiMutation<undefined, { outcome: string }>({
    method: 'POST',
    componentName: 'useHabits',
  });

  const setStatus = useCallback(
    async (id: string, status: HabitStatus): Promise<boolean> => {
      try {
        await postStatus(`/habits/${id}/status`, { status });
        refetch();
        return true;
      } catch {
        return false;
      }
    },
    [postStatus, refetch]
  );

  const remove = useCallback(
    async (id: string): Promise<boolean> => {
      try {
        await deleteOne(`/habits/${id}`, undefined);
        refetch();
        return true;
      } catch {
        return false;
      }
    },
    [deleteOne, refetch]
  );

  const removeAll = useCallback(async (): Promise<boolean> => {
    try {
      await deleteOne('/habits', undefined);
      refetch();
      return true;
    } catch {
      return false;
    }
  }, [deleteOne, refetch]);

  const recompute = useCallback(async (): Promise<boolean> => {
    try {
      await postRecompute('/habits/recompute', undefined);
      refetch();
      return true;
    } catch {
      return false;
    }
  }, [postRecompute, refetch]);

  const setEnabled = useCallback(
    async (value: boolean): Promise<boolean> => {
      try {
        await patchSettings('/habits/settings', { habits_enabled: value });
        refetch();
        return true;
      } catch {
        return false;
      }
    },
    [patchSettings, refetch]
  );

  // 404 = router not mounted (flag off) → the surface genuinely does not
  // exist. Anything else is TRANSIENT — hiding the section on a blip would
  // silently lose the feature until the next full reload.
  const notFound = error instanceof ApiError && error.status === 404;
  return {
    overview: data ?? null,
    loading,
    unavailable: notFound,
    loadError: !!error && !notFound,
    refetch,
    setStatus,
    remove,
    removeAll,
    setEnabled,
    recompute,
  };
}
