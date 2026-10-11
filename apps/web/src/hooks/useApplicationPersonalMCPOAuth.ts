'use client';

import { useEffect, useRef } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { useApplicationCommandDeadline } from '@/hooks/useApplicationCommandDeadline';
import apiClient from '@/lib/api-client';
import { navigateToAuthorizationUrl } from '@/lib/safe-navigation';
import { publishApplicationResources } from '@/lib/application-resources';
import { acceptsPersonalMCPOAuth, isPersonalMCPOAuthPending, personalMCPOAuthSelection, personalMCPOAuthURL } from '@/lib/application-personal-mcp-oauth';
import type { ApplicationCommandStatus } from '@/types/application-commands';

/** Private navigation and finalization stay bound to one actual account/command lifetime. */
export function useApplicationPersonalMCPOAuth(status: ApplicationCommandStatus, checkResult: () => Promise<void>) {
  const { user } = useAuth();
  const scope = user?.id ? `${user.id}:${status.command_id}` : undefined;
  const { lifetime, isCurrent } = useApplicationAccountLifetime(scope);
  const [mode, setMode] = useApplicationAccountState<'idle' | 'busy' | 'uncertain' | 'done' | 'pending' | 'started'>(scope, 'idle');
  const sent = useRef({ start: false, complete: false });
  const transport = useRef<AbortController | null>(null);
  const expired = useApplicationCommandDeadline(status.expires_at, scope);
  const selected = personalMCPOAuthSelection(status);
  const available = status.operation_id === 'personal_mcp.oauth_authorize' && !!selected && !expired;
  const waiting = available && status.phase === 'waiting' && status.interaction?.kind === 'device';
  const resuming = available && status.phase === 'resuming' && status.prior_outcome?.interaction?.kind === 'device';

  useEffect(() => {
    sent.current = { start: false, complete: false };
    return () => { transport.current?.abort(); transport.current = null; };
  }, [lifetime]);
  useEffect(() => {
    if (!expired) return;
    transport.current?.abort();
    if (mode === 'busy') setMode('uncertain');
  }, [expired, mode, setMode]);

  function canSubmit(stage: 'start' | 'complete') {
    return isCurrent() && mode !== 'busy' && mode !== 'uncertain' && mode !== 'done' &&
      !sent.current[stage] && Date.parse(status.expires_at) > Date.now() &&
      (stage === 'start' ? waiting : resuming);
  }

  async function start() {
    if (!canSubmit('start')) return;
    sent.current.start = true; setMode('busy');
    const request = new AbortController(); transport.current = request;
    try {
      const result = await apiClient.post<unknown>(`/application-commands/${encodeURIComponent(status.command_id)}/personal-mcp-oauth/start`, undefined,
        { cache: 'no-store', signal: request.signal });
      if (!isCurrent() || request.signal.aborted) return;
      const url = personalMCPOAuthURL(result, status.command_id);
      if (!url) throw new Error('Unusable private authorization response');
      setMode('started');
      navigateToAuthorizationUrl(url, 'application-personal-mcp-oauth');
    } catch {
      if (isCurrent()) setMode('uncertain');
    } finally {
      if (transport.current === request) transport.current = null;
    }
  }

  async function complete(onAccepted?: () => void) {
    if (!canSubmit('complete')) return;
    sent.current.complete = true; setMode('busy');
    const request = new AbortController(); transport.current = request;
    try {
      const result = await apiClient.post<unknown>(`/application-commands/${encodeURIComponent(status.command_id)}/personal-mcp-oauth/complete`, undefined,
        { cache: 'no-store', signal: request.signal });
      if (!isCurrent() || request.signal.aborted) return;
      if (!acceptsPersonalMCPOAuth(result, status)) throw new Error('Unknown authorization result');
      setMode('done');
      if (user?.id) publishApplicationResources(user.id, new Set(['user_mcp']));
      onAccepted?.();
      await checkResult().catch(() => undefined);
    } catch (error) {
      if (!isCurrent() || request.signal.aborted) return;
      if (isPersonalMCPOAuthPending(error)) { sent.current.complete = false; setMode('pending'); }
      else setMode('uncertain');
    } finally {
      if (transport.current === request) transport.current = null;
    }
  }

  return { mode, expired, waiting, resuming, start, complete };
}
