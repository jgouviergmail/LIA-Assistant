import { useCallback, useEffect, useMemo } from 'react';
import { useApiQuery } from './useApiQuery';
import { useApiMutation } from './useApiMutation';

/** Polling interval when no action is executing (ms). */
const AUTO_REFRESH_INTERVAL_MS = 30_000;
/** Faster polling interval when an action is executing (ms). */
const EXECUTING_REFRESH_INTERVAL_MS = 10_000;

/**
 * Scheduled action status types.
 */
export type ScheduledActionStatus = 'active' | 'executing' | 'error';

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
  next_trigger_at: string;
  is_enabled: boolean;
  status: ScheduledActionStatus;
  last_executed_at: string | null;
  execution_count: number;
  consecutive_failures: number;
  last_error: string | null;
  schedule_display: string;
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
}

/**
 * API list response shape.
 */
interface ScheduledActionListResponse {
  scheduled_actions: ScheduledAction[];
  total: number;
}

const ENDPOINT = '/scheduled-actions';

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
    initialData: { scheduled_actions: [], total: 0 },
  });

  const actions = listData?.scheduled_actions ?? [];
  const total = listData?.total ?? 0;

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
      }
      return result;
    },
    [createMutation, setData]
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
      }
      return result;
    },
    [updateMutation, setData]
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
    },
    [deleteMutation, setData]
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
      }
      return result;
    },
    [toggleMutation, setData]
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
    }, intervalMs);

    return () => clearInterval(interval);
  }, [refetch, intervalMs]);

  return {
    // Data
    actions,
    total,
    loading,
    error,
    refetch,

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
