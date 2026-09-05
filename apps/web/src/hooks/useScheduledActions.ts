import { useCallback, useEffect, useMemo } from 'react';
import { useApiQuery } from './useApiQuery';
import { useApiMutation } from './useApiMutation';

/** Polling interval when no action is executing (ms). */
export const AUTO_REFRESH_INTERVAL_MS = 30_000;
/** Faster polling interval when an action is executing (ms). */
export const EXECUTING_REFRESH_INTERVAL_MS = 10_000;

/**
 * Scheduled action status types.
 */
export type ScheduledActionStatus = 'active' | 'executing' | 'error';

/** N-07: how a routine decides to run at its cron tick. */
export type TriggerKind = 'time' | 'condition';

/** N-07 condition types — mirror of the backend CONDITION_TYPES. */
export type ConditionType =
  | 'task_overdue'
  | 'weather_change'
  | 'mail_match'
  | 'document_added'
  | 'calendar_event';

/** N-07 condition of a CONDITION-kind routine. */
export interface ConditionConfig {
  type: ConditionType;
  /** weather_change only (omitted = all kinds). */
  kinds?: string[];
  /** mail_match (required) / calendar_event (optional) text filter. */
  query?: string;
  /** calendar_event only: look-ahead window in hours. */
  within_hours?: number;
}

/**
 * Scheduled action from the API.
 */
export interface ScheduledAction {
  id: string;
  user_id: string;
  title: string;
  action_prompt: string;
  days_of_week: number[];
  trigger_hour: number;
  trigger_minute: number;
  user_timezone: string;
  trigger_kind: TriggerKind;
  condition_config: ConditionConfig | null;
  requires_approval: boolean;
  next_trigger_at: string;
  is_enabled: boolean;
  status: ScheduledActionStatus;
  last_executed_at: string | null;
  execution_count: number;
  consecutive_failures: number;
  last_error: string | null;
  schedule_display: string;
  /**
   * Upcoming runs as UTC instants, from the backend scheduler.
   *
   * Optional because a cached payload predating the field must still parse.
   * Never recomputed in the browser: a second reading of the cron would be a
   * second authority, and the two would disagree at the daylight-saving edges.
   */
  next_occurrences?: string[];
  created_at: string;
  updated_at: string;
}

/**
 * Create payload.
 */
export interface ScheduledActionCreate {
  title: string;
  action_prompt: string;
  days_of_week: number[];
  trigger_hour: number;
  trigger_minute: number;
  trigger_kind?: TriggerKind;
  condition_config?: ConditionConfig | null;
  requires_approval?: boolean;
}

/**
 * Update payload (partial).
 */
export interface ScheduledActionUpdate {
  title?: string;
  action_prompt?: string;
  days_of_week?: number[];
  trigger_hour?: number;
  trigger_minute?: number;
  trigger_kind?: TriggerKind;
  condition_config?: ConditionConfig | null;
  requires_approval?: boolean;
}

/** How one tick of a routine ended (mirror of the backend ScheduledRunOutcome). */
export type ScheduledRunOutcome =
  | 'success'
  | 'failure'
  | 'skipped_condition'
  | 'proposed'
  | 'skipped_hitl';

/** One configured day of the current week for one routine (ADR-265). */
export interface ScheduledActionWeekCell {
  /** ISO weekday, 1 = Monday … 7 = Sunday, in the routine's zone. */
  day: number;
  /** The local calendar date, `YYYY-MM-DD`. */
  date: string;
  /** The instant the routine fires at that day (UTC). */
  slot_at: string;
  /** How the LAST run serving this slot ended; null = no run served it. */
  outcome: ScheduledRunOutcome | null;
  run_at: string | null;
  error: string | null;
  manual: boolean | null;
}

/** The current week of one routine, cell by cell. */
export interface ScheduledActionWeek {
  id: string;
  timezone: string;
  /** The local Monday, `YYYY-MM-DD`. */
  week_start: string;
  /** ISO weekday of now in that zone — the column to highlight. */
  today: number;
  cells: ScheduledActionWeekCell[];
}

/**
 * Every routine's current week — computed server-side from the scheduler's
 * own cron engine, so the browser never re-reads a schedule; it only paints.
 */
export interface ScheduledActionWeekResponse {
  actions: ScheduledActionWeek[];
  generated_at: string;
}

/**
 * API list response shape.
 */
export interface ScheduledActionListResponse {
  scheduled_actions: ScheduledAction[];
  total: number;
}

const ENDPOINT = '/scheduled-actions';
export const WEEK_ENDPOINT = `${ENDPOINT}/week`;

/**
 * Whether a payload is the week contract.
 *
 * A hermetic browser mock answering `**\/scheduled-actions**` with the LIST
 * payload also answers `/week` with it; a shape that is not the week must
 * read as "unavailable", never crash the grid or paint from the wrong data.
 */
export function isWeekResponse(payload: unknown): payload is ScheduledActionWeekResponse {
  return (
    typeof payload === 'object' &&
    payload !== null &&
    Array.isArray((payload as { actions?: unknown }).actions)
  );
}

/**
 * Hook for scheduled actions CRUD operations.
 */
export function useScheduledActions() {
  // Query: list all
  const {
    data: listData,
    loading,
    error,
    refetch,
    setData,
  } = useApiQuery<ScheduledActionListResponse>(ENDPOINT, {
    componentName: 'ScheduledActions',
  });

  // The week states (ADR-265), polled on the same cadence as the list and
  // refetched after every mutation, since a change moves the slots.
  const { data: weekData, refetch: refetchWeek } = useApiQuery<ScheduledActionWeekResponse>(
    WEEK_ENDPOINT,
    {
      componentName: 'ScheduledActions',
    }
  );

  const actions = listData?.scheduled_actions ?? [];
  const total = listData?.total ?? 0;
  const week = isWeekResponse(weekData) ? weekData : null;
  // The FIRST load only. `useApiQuery` raises `loading` on every refetch too,
  // and swapping the section for a spinner then unmounts every card — the
  // open disclosures, the keyboard focus and the timeline fold with them.
  // Monotone by construction: `data` is only ever SET, never cleared.
  const initialLoading = listData === undefined && loading;

  // Mutations
  const createMutation = useApiMutation<ScheduledActionCreate, ScheduledAction>({
    method: 'POST',
    componentName: 'ScheduledActions',
  });

  const updateMutation = useApiMutation<ScheduledActionUpdate, ScheduledAction>({
    method: 'PATCH',
    componentName: 'ScheduledActions',
  });

  const deleteMutation = useApiMutation<void, void>({
    method: 'DELETE',
    componentName: 'ScheduledActions',
  });

  const toggleMutation = useApiMutation<void, ScheduledAction>({
    method: 'PATCH',
    componentName: 'ScheduledActions',
  });

  const executeMutation = useApiMutation<void, { status: string }>({
    method: 'POST',
    componentName: 'ScheduledActions',
  });

  // Handlers
  const createAction = useCallback(
    async (data: ScheduledActionCreate) => {
      const result = await createMutation.mutate(ENDPOINT, data);
      if (result) {
        // Optimistic: add to list
        setData(prev => {
          if (!prev) return prev;
          return {
            scheduled_actions: [...prev.scheduled_actions, result],
            total: prev.total + 1,
          };
        });
        void refetchWeek();
      }
      return result;
    },
    [createMutation, setData, refetchWeek]
  );

  const updateAction = useCallback(
    async (actionId: string, data: ScheduledActionUpdate) => {
      const result = await updateMutation.mutate(`${ENDPOINT}/${actionId}`, data);
      if (result) {
        // Optimistic: update in list
        setData(prev => {
          if (!prev) return prev;
          return {
            ...prev,
            scheduled_actions: prev.scheduled_actions.map(a => (a.id === actionId ? result : a)),
          };
        });
        void refetchWeek();
      }
      return result;
    },
    [updateMutation, setData, refetchWeek]
  );

  const deleteAction = useCallback(
    async (actionId: string) => {
      await deleteMutation.mutate(`${ENDPOINT}/${actionId}`);
      // Optimistic: remove from list
      setData(prev => {
        if (!prev) return prev;
        return {
          scheduled_actions: prev.scheduled_actions.filter(a => a.id !== actionId),
          total: prev.total - 1,
        };
      });
      void refetchWeek();
    },
    [deleteMutation, setData, refetchWeek]
  );

  const toggleAction = useCallback(
    async (actionId: string) => {
      const result = await toggleMutation.mutate(`${ENDPOINT}/${actionId}/toggle`);
      if (result) {
        // Optimistic: update in list
        setData(prev => {
          if (!prev) return prev;
          return {
            ...prev,
            scheduled_actions: prev.scheduled_actions.map(a => (a.id === actionId ? result : a)),
          };
        });
        void refetchWeek();
      }
      return result;
    },
    [toggleMutation, setData, refetchWeek]
  );

  const executeAction = useCallback(
    async (actionId: string) => {
      const result = await executeMutation.mutate(`${ENDPOINT}/${actionId}/execute`);
      if (result) {
        // Optimistic: mark as executing so faster polling kicks in immediately
        setData(prev => {
          if (!prev) return prev;
          return {
            ...prev,
            scheduled_actions: prev.scheduled_actions.map(a =>
              a.id === actionId ? { ...a, status: 'executing' as ScheduledActionStatus } : a
            ),
          };
        });
      }
      return result;
    },
    [executeMutation, setData]
  );

  // Auto-refresh: faster when actions are executing, slower otherwise
  const hasExecuting = useMemo(
    () => (listData?.scheduled_actions ?? []).some(a => a.status === 'executing'),
    [listData]
  );
  const intervalMs = hasExecuting ? EXECUTING_REFRESH_INTERVAL_MS : AUTO_REFRESH_INTERVAL_MS;

  useEffect(() => {
    const interval = setInterval(() => {
      refetch();
      refetchWeek();
    }, intervalMs);

    return () => clearInterval(interval);
  }, [refetch, refetchWeek, intervalMs]);

  return {
    // Data
    actions,
    total,
    loading,
    initialLoading,
    error,
    refetch,
    /** The current week's states, or null while unknown / unavailable. */
    week,
    refetchWeek,

    // Mutations
    createAction,
    updateAction,
    deleteAction,
    toggleAction,
    executeAction,

    // Mutation states
    creating: createMutation.loading,
    updating: updateMutation.loading,
    deleting: deleteMutation.loading,
    toggling: toggleMutation.loading,
    executing: executeMutation.loading,
  };
}
