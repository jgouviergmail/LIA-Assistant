'use client';
/** Sample native stores on the World clock, without another animation loop or poll. */
import { useCallback, useEffect, useMemo } from 'react';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useCompanionActivityStore } from '@/stores/companionActivityStore';
import { useEyesChatStore, RESTING_CHAT } from '@/stores/eyesChatStore';
import { useEyesSignalsStore } from '@/stores/eyesSignalsStore';
import { useLiveStore } from '@/stores/liveStore';
import { readCompanionSignals } from '@/components/eyes/behavior-context';
import { liveActingContext } from '@/components/eyes/rig/live-context';
import {
  deriveWorldActing,
  NEUTRAL_WORLD_ACTING,
  WorldActingEvents,
  type WorldActingFrame,
} from './world-acting';
export type WorldActingSource = (wallTime: number) => WorldActingFrame;
export function useWorldActingSource(ownerId: string, enabled: boolean): WorldActingSource {
  const { isCurrent } = useApplicationAccountLifetime(enabled ? ownerId : undefined);
  const scopeEvents = useMemo(() => ({ ownerId, events: new WorldActingEvents() }), [ownerId]);
  useEffect(() => {
    if (enabled) useCompanionActivityStore.getState().bindOwner(ownerId);
  }, [ownerId, enabled]);
  return useCallback(
    (now: number) => {
      if (!isCurrent()) return NEUTRAL_WORLD_ACTING;
      const scope = useCompanionActivityStore.getState();
      const chat = useEyesChatStore.getState();
      const signals = useEyesSignalsStore.getState();
      const live = useLiveStore.getState();
      const liveRecord = live.sessionId ? live.lastActivity : null;
      const recent =
        liveRecord && liveRecord.at > (signals.lastActivity?.at ?? 0)
          ? liveRecord
          : signals.lastActivity;
      const frame = deriveWorldActing({
        ownerId,
        signalOwnerId: scope.ownerId,
        enabled,
        now,
        expression: {
          ...(chat.ownerId === ownerId ? chat.state : RESTING_CHAT),
          ...readCompanionSignals(now),
          inactivityStage: 0,
        },
        context: liveActingContext(now),
        recent,
        runId:
          recent === liveRecord && liveRecord ? liveRecord.event.run_id : signals.activityRunId,
        background: scope.sample,
        emphasis: signals.liveEmphasis(now),
        responseWeight: signals.liveReactionWeight(now),
      });
      return frame.eventKey && !scopeEvents.events.take(frame.eventKey)
        ? { ...frame, eventKey: null }
        : frame;
    },
    [ownerId, enabled, isCurrent, scopeEvents]
  );
}
