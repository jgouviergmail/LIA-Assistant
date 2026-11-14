import { useCallback } from 'react';

import type { RoutineWebhookSecret } from './useScheduledActions';
import { useApiMutation } from './useApiMutation';

const ENDPOINT = '/scheduled-actions';

/**
 * Draw a new secret for a routine started by calls (ADR-386).
 *
 * Its own hook, apart from the routines' CRUD: the route is closed by the
 * `routine_webhooks` capability, so only a screen that reads that door may
 * import it (`capability-callers.guard.test.ts`) — the dashboard's starter card
 * reads the routines and must not reach a route the switch closes.
 *
 * The answer is the only place a secret ever is: the caller shows it once, and
 * nothing here keeps it.
 */
export function useRoutineWebhookSecret() {
  const mutation = useApiMutation<void, RoutineWebhookSecret>({
    method: 'POST',
    componentName: 'ScheduledActions',
  });

  const drawWebhookSecret = useCallback(
    async (actionId: string) => mutation.mutate(`${ENDPOINT}/${actionId}/webhook-secret`),
    [mutation]
  );

  return { drawWebhookSecret, drawingSecret: mutation.loading };
}
