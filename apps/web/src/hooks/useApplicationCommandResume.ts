'use client';

import { useCallback, useEffect, useRef } from 'react';
import { useAuth } from '@/hooks/useAuth';
import {
  useApplicationAccountLifetime,
  type ApplicationAccountLifetime,
} from '@/hooks/useApplicationAccountLifetime';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { useApplicationCommandStatus } from '@/hooks/useApplicationCommandStatus';
import { useStepUpGuard } from '@/hooks/useStepUpGuard';
import apiClient from '@/lib/api-client';
import { publishApplicationResources } from '@/lib/application-resources';
import { secureActionPresentation } from '@/lib/application-secure-actions';

/** Each click is bound to the current account and command; a lost response is observed. */
export function useApplicationCommandResume(commandId: string) {
  const { user } = useAuth();
  const scopeKey = user?.id ? `${user.id}:${commandId}` : undefined;
  const { lifetime, isCurrent } = useApplicationAccountLifetime(scopeKey);
  const [mode, setMode] = useApplicationAccountState<'idle' | 'busy' | 'uncertain'>(
    scopeKey,
    'idle'
  );
  const inFlight = useRef<ApplicationAccountLifetime | null>(null);
  const stepUp = useStepUpGuard({ ownerId: scopeKey });
  const observation = useApplicationCommandStatus(commandId);
  const { status, refresh, observe } = observation;
  const { guard } = stepUp;

  useEffect(() => {
    const presentation = status && secureActionPresentation(status.operation_id);
    if (presentation && status && ['committed', 'failed'].includes(status.phase) && user?.id) {
      publishApplicationResources(user.id, new Set([presentation.resource]));
    }
  }, [status, user?.id]);
  useEffect(() => {
    if (status?.phase !== 'waiting') return;
    const delay = Math.max(0, new Date(status.expires_at).getTime() - Date.now());
    const timer = setTimeout(() => {
      void refresh();
    }, delay);
    return () => {
      clearTimeout(timer);
    };
  }, [status?.phase, status?.expires_at, refresh]);

  const resume = useCallback(async () => {
    if (!isCurrent() || inFlight.current === lifetime || mode !== 'idle') return;
    if (
      status?.phase !== 'waiting' ||
      status.interaction?.kind !== 'secure' ||
      !secureActionPresentation(status.operation_id)
    )
      return;
    if (new Date(status.expires_at).getTime() <= Date.now()) {
      await refresh();
      return;
    }
    inFlight.current = lifetime;
    setMode('busy');
    try {
      const result = await guard(() =>
        apiClient.post<unknown>(`/application-commands/${encodeURIComponent(commandId)}/resume`)
      );
      if (isCurrent()) {
        observe(result);
        setMode('idle');
      }
    } catch {
      if (isCurrent()) setMode('uncertain');
    } finally {
      if (inFlight.current === lifetime) inFlight.current = null;
    }
    return isCurrent();
  }, [commandId, guard, isCurrent, lifetime, mode, observe, refresh, setMode, status]);
  const checkResult = useCallback(async () => {
    if (isCurrent() && inFlight.current !== lifetime && (await refresh())) setMode('idle');
  }, [isCurrent, lifetime, refresh, setMode]);
  return {
    status,
    mode,
    readError: observation.error,
    resume,
    checkResult,
    observation,
    dialogKey: scopeKey,
    stepUpOpen: stepUp.stepUpOpen,
    onVerified: stepUp.onVerified,
    onCancel: stepUp.onCancel,
  };
}
