'use client';

import { useEffect, useRef } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { useApplicationCommandDeadline } from '@/hooks/useApplicationCommandDeadline';
import apiClient from '@/lib/api-client';
import { publishApplicationResources } from '@/lib/application-resources';
import { acceptsPersonalMCPConfiguration, personalMCPConfigurationSelection, personalMCPFormListSchema } from '@/lib/application-personal-mcp-configuration';
import { editMCPServerForm, emptyMCPServerForm, isMCPServerFormValid, mcpServerFormValues, type MCPServerFormSource } from '@/lib/mcp-server-form';
import type { ApplicationCommandStatus } from '@/types/application-commands';

/** Secrets have one local account/command lifetime; only the explicit Save submits them. */
export function useApplicationPersonalMCPConfiguration(status: ApplicationCommandStatus, checkResult: () => Promise<void>) {
  const { user } = useAuth();
  const scope = user?.id ? `${user.id}:${status.command_id}` : undefined;
  const { lifetime, isCurrent } = useApplicationAccountLifetime(scope);
  const [open, setOpen] = useApplicationAccountState(scope, false);
  const [form, setForm] = useApplicationAccountState(scope, emptyMCPServerForm());
  const [server, setServer] = useApplicationAccountState<MCPServerFormSource | null>(scope, null);
  const [ready, setReady] = useApplicationAccountState(scope, false);
  const [loading, setLoading] = useApplicationAccountState(scope, false);
  const [loadFailed, setLoadFailed] = useApplicationAccountState(scope, false);
  const [mode, setMode] = useApplicationAccountState<'idle' | 'busy' | 'done' | 'uncertain'>(scope, 'idle');
  const transport = useRef<AbortController | null>(null);
  const started = useRef(false);
  const expired = useApplicationCommandDeadline(status.expires_at, scope);
  const selected = personalMCPConfigurationSelection(status);
  const waiting = status.operation_id === 'personal_mcp.configuration' && status.phase === 'waiting' &&
    status.interaction?.kind === 'device' && !!selected && !expired;

  useEffect(() => {
    started.current = false;
    return () => { transport.current?.abort(); transport.current = null; };
  }, [lifetime]);
  useEffect(() => {
    if (waiting) return;
    transport.current?.abort();
    setOpen(false); setForm(emptyMCPServerForm()); setServer(null); setReady(false); setLoading(false);
    if (started.current && mode === 'busy') setMode('uncertain');
  }, [waiting, mode, setMode, setOpen, setForm, setServer, setReady, setLoading]);

  function canEdit() {
    return isCurrent() && waiting && mode === 'idle' && !started.current && !loading;
  }

  async function showForm() {
    if (!canEdit()) return;
    setOpen(true); setLoadFailed(false);
    if (ready) return;
    if (selected?.creating) { setReady(true); return; }
    const request = new AbortController(); transport.current?.abort(); transport.current = request;
    setLoading(true);
    try {
      const list = personalMCPFormListSchema.parse(await apiClient.get<unknown>('/mcp/servers', {
        cache: 'no-store', signal: request.signal,
      }));
      if (!isCurrent() || request.signal.aborted) return;
      const existing = list.servers.find(item => item.id === selected?.server_id);
      if (!existing) throw new Error('Unavailable owned configuration');
      setServer(existing); setForm(editMCPServerForm(existing)); setReady(true);
    } catch {
      if (isCurrent() && !request.signal.aborted) setLoadFailed(true);
    } finally {
      if (isCurrent() && transport.current === request) { setLoading(false); transport.current = null; }
    }
  }

  function closeForm() {
    transport.current?.abort(); transport.current = null;
    setOpen(false); setForm(emptyMCPServerForm()); setServer(null); setReady(false); setLoading(false);
    if (started.current && mode === 'busy') setMode('uncertain');
  }

  async function save(onAccepted?: () => void) {
    const deadline = Date.parse(status.expires_at);
    if (!canEdit() || !ready ||
      !Number.isFinite(deadline) || deadline <= Date.now() || !isMCPServerFormValid(form, !!server)) return;
    started.current = true; setMode('busy');
    const request = new AbortController(); transport.current = request;
    try {
      const result = await apiClient.post<unknown>(`/application-commands/${encodeURIComponent(status.command_id)}/personal-mcp`, {
        values: mcpServerFormValues(form, server),
      }, { cache: 'no-store', signal: request.signal });
      if (!isCurrent()) return;
      if (!acceptsPersonalMCPConfiguration(result, status)) throw new Error('Unknown configuration result');
      setMode('done'); setOpen(false); setForm(emptyMCPServerForm()); setServer(null); setReady(false);
      if (user?.id) publishApplicationResources(user.id, new Set(['user_mcp']));
      onAccepted?.();
      void Promise.resolve(checkResult()).catch(() => {});
    } catch {
      if (isCurrent()) { setMode('uncertain'); closeForm(); }
    } finally {
      if (transport.current === request) transport.current = null;
    }
  }
  return { open, form, setForm, server, ready, loading, loadFailed, mode, expired, waiting, showForm, closeForm, save };
}
