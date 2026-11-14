'use client';

import { useContext, useEffect, useRef } from 'react';
import { AppConfigSeedContext } from '@/hooks/useAppConfig';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { useApplicationCommandDeadline } from '@/hooks/useApplicationCommandDeadline';
import apiClient from '@/lib/api-client';
import { capabilityAvailable } from '@/lib/capability-availability';
import { publishApplicationResources } from '@/lib/application-resources';
import {
  acceptsPersonalMCPConfiguration,
  personalMCPConfigurationSelection,
  personalMCPFormListSchema,
} from '@/lib/application-personal-mcp-configuration';
import { applyKnownServer, knownMCPServerListSchema } from '@/lib/mcp-known-servers';
import {
  editMCPServerForm,
  emptyMCPServerForm,
  isMCPServerFormValid,
  mcpServerFormValues,
  type MCPServerFormSource,
  type MCPServerFormState,
} from '@/lib/mcp-server-form';
import type { ApplicationCommandStatus } from '@/types/application-commands';

/** What the private form starts from: the saved server it edits, if any, and its fields. */
interface FormStart {
  server: MCPServerFormSource | null;
  form: MCPServerFormState;
}

/** The saved server a confirmation edits; it throws once that server is not owned any more. */
async function ownedServerStart(
  serverId: string | null | undefined,
  signal: AbortSignal
): Promise<FormStart> {
  const list = personalMCPFormListSchema.parse(
    await apiClient.get<unknown>('/mcp/servers', { cache: 'no-store', signal })
  );
  const existing = list.servers.find(item => item.id === serverId);
  if (!existing) throw new Error('Unavailable owned configuration');
  return { server: existing, form: editMCPServerForm(existing) };
}

/**
 * A new server the assistant proposed from the known catalogue: its PUBLIC
 * name, address and sign-in method, read from the API by its key. A catalogue
 * that cannot be read, or that no longer lists the key, costs the prefill and
 * never the form — the address can still be typed, or another server picked.
 */
async function knownServerStart(key: string, signal: AbortSignal): Promise<FormStart> {
  const empty = { server: null, form: emptyMCPServerForm() };
  try {
    const list = knownMCPServerListSchema.parse(
      await apiClient.get<unknown>('/mcp/servers/known', { cache: 'no-store', signal })
    );
    const known = list.servers.find(server => server.key === key);
    return known ? { server: null, form: applyKnownServer(empty.form, known) } : empty;
  } catch {
    return empty;
  }
}

/**
 * The read a confirmation's form starts from, or null where it starts empty and
 * nothing is read: a new server the person types themselves.
 */
function startReader(
  selected: ReturnType<typeof personalMCPConfigurationSelection>
): ((signal: AbortSignal) => Promise<FormStart>) | null {
  if (!selected?.creating) return signal => ownedServerStart(selected?.server_id, signal);
  const key = selected.known_server;
  return key ? signal => knownServerStart(key, signal) : null;
}

/** Secrets have one local account/command lifetime; only the explicit Save submits them. */
export function useApplicationPersonalMCPConfiguration(
  status: ApplicationCommandStatus,
  checkResult: () => Promise<void>
) {
  const { user } = useAuth();
  const scope = user?.id ? `${user.id}:${status.command_id}` : undefined;
  const { lifetime, isCurrent } = useApplicationAccountLifetime(scope);
  const [open, setOpen] = useApplicationAccountState(scope, false);
  const [form, setForm] = useApplicationAccountState(scope, emptyMCPServerForm());
  const [server, setServer] = useApplicationAccountState<MCPServerFormSource | null>(scope, null);
  const [ready, setReady] = useApplicationAccountState(scope, false);
  const [loading, setLoading] = useApplicationAccountState(scope, false);
  const [loadFailed, setLoadFailed] = useApplicationAccountState(scope, false);
  const [mode, setMode] = useApplicationAccountState<'idle' | 'busy' | 'done' | 'uncertain'>(
    scope,
    'idle'
  );
  const transport = useRef<AbortController | null>(null);
  const started = useRef(false);
  const expired = useApplicationCommandDeadline(status.expires_at, scope);
  const selected = personalMCPConfigurationSelection(status);
  const awaited =
    status.operation_id === 'personal_mcp.configuration' &&
    status.phase === 'waiting' &&
    status.interaction?.kind === 'device' &&
    !!selected &&
    !expired;
  // The personal servers' router refuses every route under the operator's
  // switch (ADR-280): the form is offered only where the layout's read of
  // `/config` says the servers are, and a form the switch overtakes closes
  // below like one whose confirmation expired. Before that read answers the
  // form is not offered yet — and nothing is claimed closed.
  const config = useContext(AppConfigSeedContext);
  const offered = capabilityAvailable(config, 'mcp');
  const waiting = awaited && offered;
  const closed = awaited && config !== null && !offered;

  useEffect(() => {
    started.current = false;
    return () => {
      transport.current?.abort();
      transport.current = null;
    };
  }, [lifetime]);
  useEffect(() => {
    if (waiting) return;
    transport.current?.abort();
    setOpen(false);
    setForm(emptyMCPServerForm());
    setServer(null);
    setReady(false);
    setLoading(false);
    if (started.current && mode === 'busy') setMode('uncertain');
  }, [waiting, mode, setMode, setOpen, setForm, setServer, setReady, setLoading]);

  function canEdit() {
    return isCurrent() && waiting && mode === 'idle' && !started.current && !loading;
  }

  async function showForm() {
    if (!canEdit()) return;
    setOpen(true);
    setLoadFailed(false);
    if (ready) return;
    const readStart = startReader(selected);
    if (!readStart) {
      setReady(true);
      return;
    }
    const request = new AbortController();
    transport.current?.abort();
    transport.current = request;
    setLoading(true);
    try {
      const start = await readStart(request.signal);
      if (!isCurrent() || request.signal.aborted) return;
      setServer(start.server);
      setForm(start.form);
      setReady(true);
    } catch {
      if (isCurrent() && !request.signal.aborted) setLoadFailed(true);
    } finally {
      if (isCurrent() && transport.current === request) {
        setLoading(false);
        transport.current = null;
      }
    }
  }

  function closeForm() {
    transport.current?.abort();
    transport.current = null;
    setOpen(false);
    setForm(emptyMCPServerForm());
    setServer(null);
    setReady(false);
    setLoading(false);
    if (started.current && mode === 'busy') setMode('uncertain');
  }

  async function save(onAccepted?: () => void) {
    const deadline = Date.parse(status.expires_at);
    if (
      !canEdit() ||
      !ready ||
      !Number.isFinite(deadline) ||
      deadline <= Date.now() ||
      !isMCPServerFormValid(form, server)
    )
      return;
    started.current = true;
    setMode('busy');
    const request = new AbortController();
    transport.current = request;
    try {
      const result = await apiClient.post<unknown>(
        `/application-commands/${encodeURIComponent(status.command_id)}/personal-mcp`,
        {
          values: mcpServerFormValues(form, server),
        },
        { cache: 'no-store', signal: request.signal }
      );
      if (!isCurrent()) return;
      if (!acceptsPersonalMCPConfiguration(result, status))
        throw new Error('Unknown configuration result');
      setMode('done');
      setOpen(false);
      setForm(emptyMCPServerForm());
      setServer(null);
      setReady(false);
      if (user?.id) publishApplicationResources(user.id, new Set(['user_mcp']));
      onAccepted?.();
      void Promise.resolve(checkResult()).catch(() => {});
    } catch {
      if (isCurrent()) {
        setMode('uncertain');
        closeForm();
      }
    } finally {
      if (transport.current === request) transport.current = null;
    }
  }
  return {
    open,
    form,
    setForm,
    server,
    ready,
    loading,
    loadFailed,
    mode,
    expired,
    waiting,
    closed,
    showForm,
    closeForm,
    save,
  };
}
