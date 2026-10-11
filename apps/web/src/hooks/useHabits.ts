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
import { z } from '@/lib/zod';

import { ApiError } from '@/lib/api-client';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';

const releaseHabitOverride = () => {};

const habitForgetResponse = z.object({
  deleted_habits: z.number().int().nonnegative(),
  profile_deleted: z.boolean(),
  advisory_cleanup_confirmed: z.boolean().default(false),
});
export type HabitForgetOutcome = 'complete' | 'partial' | 'failed';

function forgettingOutcome(response: unknown, current: boolean): HabitForgetOutcome {
  if (!current) return 'failed';
  const parsed = habitForgetResponse.safeParse(response);
  if (!parsed.success || !parsed.data.profile_deleted) return 'failed';
  return parsed.data.advisory_cleanup_confirmed ? 'complete' : 'partial';
}

export type HabitVerdict = 'windows' | 'diffuse' | 'none' | 'insufficient' | 'sparse';

/** The analyzer's closed `immediate_intent` vocabulary (backend
 * `IMMEDIATE_INTENTS`) — the request descriptor a recurring habit may carry
 * (`payload.usual_intent`, ADR-214 c). The only values the panel translates:
 * a payload carrying anything else (a model's stray spelling) falls back to
 * the plain wording, because a raw token is not a label. Pinned to the
 * `settings.habits.intent.*` locale keys by `useHabits.test.ts`. */
export const HABIT_INTENTS = [
  'search',
  'detail',
  'create',
  'update',
  'delete',
  'send',
  'chat',
  'list',
] as const;
export type HabitIntent = (typeof HABIT_INTENTS)[number];

/** Narrow an arbitrary payload value to a translatable intent, or null. */
export function habitIntentOf(value: unknown): HabitIntent | null {
  return typeof value === 'string' && (HABIT_INTENTS as readonly string[]).includes(value)
    ? (value as HabitIntent)
    : null;
}
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
  /** Provenance: typed turns, or rebuilt from durable history by the recompute
   * (stated on screen, never a different threshold — ADR-214 amendment). */
  origin: 'live' | 'seed';
}

export interface HabitsStreak {
  /** Consecutive active days ending today or yesterday (grace rule). */
  current: number;
  longest: number;
  milestone_reached: number | null;
  next_milestone: number | null;
}

export interface HabitsOverview {
  habits_enabled: boolean;
  profile: HabitsProfile;
  /** Ledger-derived streaks (Lot 1-A4) — display only. */
  streak: HabitsStreak;
  habits: Habit[];
  /** Recurrence signatures under observation (capped server-side). */
  candidates: HabitCandidate[];
  /** Candidates beyond the display cap — a cap is stated, never silent. */
  candidates_more: number;
  /** Whether this instance lets LIA offer an automation in the chat when a
   * recurring request locks (RECURRENCE_SUGGESTION_ENABLED). Learning and the
   * heartbeat offers do not depend on it; the panel says so (ADR-184). */
  chat_suggestions_enabled: boolean;
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
  removeAll: () => Promise<HabitForgetOutcome>;
  setEnabled: (enabled: boolean) => Promise<boolean>;
  /** Run the nightly unit of work NOW (retroactive over existing history). */
  recompute: () => Promise<boolean>;
}

export function useHabits(enabled = true): UseHabitsReturn {
  const { data, loading, error, refetch, ownerId, isCurrent } =
    useApplicationAccountQuery<HabitsOverview>('/habits', 'useHabits', enabled);
  useApplicationResourceSync(ownerId, 'habits', refetch, releaseHabitOverride);
  const retry = useCallback(() => {
    void refetch().catch(() => undefined);
  }, [refetch]);

  const { mutate: postStatus } = useApiMutation<{ status: HabitStatus }, Habit>({
    method: 'POST',
    componentName: 'useHabits',
  });
  const { mutate: deleteOne } = useApiMutation<undefined, unknown>({
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
      if (!isCurrent()) return false;
      try {
        await postStatus(`/habits/${id}/status`, { status });
        await refetch();
        return isCurrent();
      } catch {
        return false;
      }
    },
    [postStatus, refetch, isCurrent]
  );

  const remove = useCallback(
    async (id: string): Promise<boolean> => {
      if (!isCurrent()) return false;
      try {
        await deleteOne(`/habits/${id}`, undefined);
        await refetch();
        return isCurrent();
      } catch {
        return false;
      }
    },
    [deleteOne, refetch, isCurrent]
  );

  const removeAll = useCallback(async (): Promise<HabitForgetOutcome> => {
    if (!isCurrent()) return 'failed';
    try {
      const response = await deleteOne('/habits', undefined);
      await refetch();
      return forgettingOutcome(response, isCurrent());
    } catch {
      return 'failed';
    }
  }, [deleteOne, refetch, isCurrent]);

  const recompute = useCallback(async (): Promise<boolean> => {
    if (!isCurrent()) return false;
    try {
      await postRecompute('/habits/recompute', undefined);
      await refetch();
      return isCurrent();
    } catch {
      return false;
    }
  }, [postRecompute, refetch, isCurrent]);

  const setEnabled = useCallback(
    async (value: boolean): Promise<boolean> => {
      if (!isCurrent()) return false;
      try {
        await patchSettings('/habits/settings', { habits_enabled: value });
        await refetch();
        return isCurrent();
      } catch {
        return false;
      }
    },
    [patchSettings, refetch, isCurrent]
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
    refetch: retry,
    setStatus,
    remove,
    removeAll,
    setEnabled,
    recompute,
  };
}
