/**
 * The reminders a reader owns, and the three things they can do to them.
 *
 * Reminders had no hook: they were created by conversation and read on the
 * briefing card through the briefing payload. The owner reversed that on
 * 2026-09-06, so this is the data access for the settings screen.
 *
 * **The list is never a history.** A reminder is deleted the moment it has no
 * future left — a single occurrence after it fires, a bounded series after its
 * last instant — so what comes back is always what is still coming. There is
 * no "past reminders" endpoint to add later; there is nothing behind them.
 *
 * The shape mirrors `useScheduledActions` deliberately: one `useApiQuery`, one
 * mutation per verb, optimistic list updates, and an `initialLoading` that is
 * monotone so a poll never unmounts the section (the `PeerConnectionsSettings`
 * defect, `apps/web/CLAUDE.md`).
 */

import { useCallback } from 'react';

import type { RecurrenceSpec } from '@/types/recurrence';

import { useApiMutation } from './useApiMutation';
import { useApiQuery } from './useApiQuery';

const ENDPOINT = '/reminders';
const DETAIL_ENDPOINT = '/reminders/detail';

/**
 * The page the screen asks for — the API maximum.
 *
 * Reminders have no per-user ceiling (routines do: 20). Asking for the default
 * 25 and rendering an exact total of 80 beside them would be a cap applied in
 * silence, which ADR-185 forbids: the screen states what it could not show.
 */
export const REMINDERS_PAGE_SIZE = 100;

/** One reminder, as the management screen reads it. */
export interface Reminder {
  id: string;
  content: string;
  /** UTC instant of the NEXT firing — never null: a reminder always has one. */
  trigger_at: string;
  user_timezone: string;
  recurrence: RecurrenceSpec;
  /** The schedule in the reader's own words, composed server-side. */
  schedule_display: string;
  /** `HH:MM`, ascending, resolved server-side — never expanded here. */
  times_of_day: string[];
  runs_per_day: number;
  next_occurrences: string[];
  created_at: string;
}

export interface ReminderListResponse {
  reminders: Reminder[];
  /** EXACT count behind the page, not the page length (ADR-185). */
  total: number;
}

/**
 * Creating a reminder: EITHER an instant or a schedule, never both.
 *
 * The API refuses both together and derives the armed instant from the
 * recurrence when one is given. Sending a `trigger_at` beside a recurrence
 * would be a second authority on when the reminder fires — the card would
 * announce one time and the notification arrive at another.
 */
export interface ReminderCreate {
  content: string;
  original_message: string;
  /** Local wall clock of a SINGLE firing; omit when sending a recurrence. */
  trigger_at?: string;
  recurrence?: RecurrenceSpec;
}

export interface ReminderUpdate {
  content?: string;
  trigger_at?: string;
  /** Replaced WHOLE; omit to leave the schedule alone. Never send null. */
  recurrence?: RecurrenceSpec;
}

export function useReminders() {
  const { data, loading, error, refetch, setData } = useApiQuery<ReminderListResponse>(
    `${DETAIL_ENDPOINT}?limit=${REMINDERS_PAGE_SIZE}`,
    {
      componentName: 'Reminders',
    }
  );

  const reminders = data?.reminders ?? [];
  const total = data?.total ?? 0;
  // FIRST load only, and monotone: `data` is only ever set, never cleared, so
  // a refresh cannot swap the populated section for a spinner and destroy the
  // reader's place in it.
  const initialLoading = data === undefined && loading;

  const createMutation = useApiMutation<ReminderCreate, Reminder>({
    method: 'POST',
    componentName: 'Reminders',
  });
  const updateMutation = useApiMutation<ReminderUpdate, Reminder>({
    method: 'PATCH',
    componentName: 'Reminders',
  });
  const deleteMutation = useApiMutation<void, void>({
    method: 'DELETE',
    componentName: 'Reminders',
  });

  const createReminder = useCallback(
    async (payload: ReminderCreate) => {
      const created = await createMutation.mutate(ENDPOINT, payload);
      if (created) {
        setData(prev =>
          prev ? { reminders: [...prev.reminders, created], total: prev.total + 1 } : prev
        );
      }
      return created;
    },
    [createMutation, setData]
  );

  const updateReminder = useCallback(
    async (reminderId: string, payload: ReminderUpdate) => {
      const updated = await updateMutation.mutate(`${ENDPOINT}/${reminderId}`, payload);
      if (updated) {
        setData(prev =>
          prev
            ? {
                ...prev,
                reminders: prev.reminders.map(r => (r.id === reminderId ? updated : r)),
              }
            : prev
        );
      }
      return updated;
    },
    [updateMutation, setData]
  );

  const deleteReminder = useCallback(
    async (reminderId: string) => {
      await deleteMutation.mutate(`${ENDPOINT}/${reminderId}`);
      setData(prev =>
        prev
          ? {
              reminders: prev.reminders.filter(r => r.id !== reminderId),
              total: Math.max(prev.total - 1, 0),
            }
          : prev
      );
    },
    [deleteMutation, setData]
  );

  return {
    reminders,
    total,
    loading,
    initialLoading,
    error,
    refetch,
    createReminder,
    updateReminder,
    deleteReminder,
    creating: createMutation.loading,
    updating: updateMutation.loading,
    deleting: deleteMutation.loading,
  };
}
