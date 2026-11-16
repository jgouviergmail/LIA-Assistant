/**
 * A fired reminder's state and its presses (ADR-268 amendment 2026-11-16).
 *
 * The state is read once a surface shows the occurrence
 * (`GET /reminders/firings/{id}`); a press posts, and its verdict is remembered
 * page-wide (`recordFiringVerdict`) so every surface showing the same occurrence
 * follows it — the toast's press settles the bubble. A press that fails throws:
 * the caller says it.
 */

import { useCallback } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';
import {
  firingEndpoint,
  recordFiringVerdict,
  snoozeVerdictOf,
  useFiringVerdict,
  type FiringVerdict,
  type ReminderFiringState,
  type SnoozeChoice,
  type SnoozeSurface,
  type SnoozeVerdict,
  type StopVerdict,
} from '@/lib/reminder-firing';

const COMPONENT = 'ReminderFiring';

/** The snooze press, for any occurrence: the toast knows only its id. */
export function useSnoozeFiring(surface: SnoozeSurface = 'chat'): {
  snooze: (firingId: string, choice: SnoozeChoice) => Promise<SnoozeVerdict | undefined>;
  loading: boolean;
} {
  const { mutate, loading } = useApiMutation<
    { choice: SnoozeChoice; surface: SnoozeSurface },
    SnoozeVerdict
  >({ method: 'POST', componentName: COMPONENT, retainResponse: false });

  const snooze = useCallback(
    async (firingId: string, choice: SnoozeChoice): Promise<SnoozeVerdict | undefined> => {
      const answer = await mutate(`${firingEndpoint(firingId)}/snooze`, { choice, surface });
      const settled = answer ? snoozeVerdictOf(answer) : null;
      if (settled) recordFiringVerdict(firingId, settled);
      return answer;
    },
    [mutate, surface]
  );
  return { snooze, loading };
}

export interface UseReminderFiringResult {
  /** The server's state, once read; undefined before, or when the read failed. */
  state: ReminderFiringState | undefined;
  /** The read failed (purged, foreign, unreachable): the surface offers nothing. */
  unavailable: boolean;
  /** What this page learned since the read. */
  verdict: FiringVerdict | undefined;
  /** A press is under way. */
  busy: boolean;
  snooze: (choice: SnoozeChoice) => Promise<SnoozeVerdict | undefined>;
  stop: () => Promise<StopVerdict | undefined>;
}

/**
 * Read and act on one fired occurrence.
 *
 * @param firingId - The occurrence, or null to read nothing.
 * @returns Its state, the page's verdict and the two presses.
 */
export function useReminderFiring(firingId: string | null): UseReminderFiringResult {
  const { data, error } = useApiQuery<ReminderFiringState>(firingEndpoint(firingId ?? ''), {
    componentName: COMPONENT,
    enabled: firingId !== null,
  });
  const verdict = useFiringVerdict(firingId);
  const { snooze: snoozeFiring, loading: snoozing } = useSnoozeFiring('chat');
  const { mutate: postStop, loading: stopping } = useApiMutation<undefined, StopVerdict>({
    method: 'POST',
    componentName: COMPONENT,
    retainResponse: false,
  });

  const snooze = useCallback(
    async (choice: SnoozeChoice): Promise<SnoozeVerdict | undefined> =>
      firingId ? snoozeFiring(firingId, choice) : undefined,
    [firingId, snoozeFiring]
  );

  const stop = useCallback(async (): Promise<StopVerdict | undefined> => {
    if (!firingId) return undefined;
    const answer = await postStop(`${firingEndpoint(firingId)}/stop`);
    if (answer) recordFiringVerdict(firingId, { stopped: true });
    return answer;
  }, [firingId, postStop]);

  return {
    state: data,
    unavailable: error !== null,
    verdict,
    busy: snoozing || stopping,
    snooze,
    stop,
  };
}
