'use client';

import { useCallback } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { ApiError } from '@/lib/api-client';
import { z } from '@/lib/zod';
import { applicationCommandStatusSchema, type ApplicationCommandStatus } from '@/types/application-commands';

/** Account and command lifetimes fence refreshes and every accepted response. */
export function useApplicationCommandStatus(commandId: string | null | undefined) {
  const { user } = useAuth();
  const valid = z.string().uuid().safeParse(commandId).success;
  const scopeKey = user?.id && valid ? `${user.id}:${commandId}` : undefined;
  const { isCurrent } = useApplicationAccountLifetime(scopeKey);
  const [status, setStatus] = useApplicationAccountState<ApplicationCommandStatus | null>(scopeKey, null);
  const onSuccess = useCallback((response: unknown) => {
    if (!isCurrent()) return;
    const parsed = applicationCommandStatusSchema.safeParse(response);
    if (!parsed.success || parsed.data.command_id !== commandId) {
      // Never log parser issues: a malformed server payload may contain private data.
      throw new Error('Invalid application command response');
    }
    setStatus(parsed.data);
  }, [commandId, isCurrent, setStatus]);
  const onError = useCallback((failure: Error) => {
    if (!isCurrent()) return;
    if (failure instanceof ApiError && [401, 403, 404].includes(failure.status)) setStatus(null);
  }, [isCurrent, setStatus]);
  const query = useApiQuery<unknown>(`/application-commands/${encodeURIComponent(commandId ?? '')}`, {
    componentName: 'useApplicationCommandStatus', enabled: !!scopeKey,
    deps: [scopeKey], onSuccess, onError,
  });
  const { refetchVerified } = query;
  const refresh = useCallback(async () => {
    if (isCurrent()) return await refetchVerified();
    return false;
  }, [isCurrent, refetchVerified]);
  return { status, loading: query.loading, error: query.error, refresh, observe: onSuccess };
}
