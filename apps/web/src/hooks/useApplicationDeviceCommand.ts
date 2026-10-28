'use client';

import { useCallback, useRef } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import type { useApplicationCommandStatus } from '@/hooks/useApplicationCommandStatus';
import {
  continueRecordingDeviceCommand,
  isWaitingRecordingCommand,
} from '@/lib/application-device-continuation';
import { publishApplicationResources } from '@/lib/application-resources';

/** A lost claim/ACK is observed; an effect is never retried on that account. */
export function useApplicationDeviceCommand(
  commandId: string,
  observation: ReturnType<typeof useApplicationCommandStatus>
) {
  const { user } = useAuth();
  const userId = user?.id;
  const scope = userId ? `${userId}:${commandId}` : undefined;
  const { lifetime, isCurrent } = useApplicationAccountLifetime(scope);
  const [mode, setMode] = useApplicationAccountState<'idle' | 'busy' | 'uncertain'>(scope, 'idle');
  const inFlight = useRef<object | null>(null);
  const { status, refresh, observe } = observation;
  const execute = useCallback(async () => {
    if (
      !userId ||
      !isCurrent() ||
      mode !== 'idle' ||
      inFlight.current === lifetime ||
      !isWaitingRecordingCommand(status)
    )
      return;
    if (Date.parse(status.expires_at) <= Date.now()) {
      await refresh();
      return;
    }
    inFlight.current = lifetime;
    setMode('busy');
    try {
      const result = await continueRecordingDeviceCommand(userId, commandId, isCurrent);
      if (!isCurrent()) return;
      if (result === null) {
        await refresh();
        if (isCurrent()) setMode('uncertain');
        return isCurrent();
      }
      observe(result);
      publishApplicationResources(userId, new Set(['meetings']));
      setMode('idle');
    } catch {
      if (isCurrent()) setMode('uncertain');
    } finally {
      if (inFlight.current === lifetime) inFlight.current = null;
    }
    return isCurrent();
  }, [userId, isCurrent, mode, lifetime, status, refresh, setMode, commandId, observe]);
  return { ...observation, mode, execute, checkResult: refresh };
}
