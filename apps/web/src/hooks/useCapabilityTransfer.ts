'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import apiClient from '@/lib/api-client';
import {
  capabilityTransferSchema,
  type CapabilitySelection,
  type CapabilityTransfer,
} from '@/lib/capability-sharing';
import { useAuth } from './useAuth';
import { useApplicationAccountLifetime } from './useApplicationAccountLifetime';

interface State {
  preview: CapabilityTransfer | null;
  outcome: CapabilityTransfer | null;
  pending: boolean;
  error: Error | null;
}
const INITIAL: State = { preview: null, outcome: null, pending: false, error: null };
type Result = { type: 'preview' | 'outcome'; value: CapabilityTransfer };
interface Scoped<T> {
  scope: object;
  value: T;
}
interface Operation {
  scope: object;
  token: symbol;
  controller: AbortController;
}

function parseReceipt(data: unknown, source: CapabilitySelection, previous?: CapabilityTransfer) {
  const receipt = capabilityTransferSchema.parse(data);
  if (
    receipt.kind !== source.kind ||
    (previous && (receipt.id !== previous.id || receipt.digest !== previous.digest))
  ) {
    throw new Error('capability_share.invalid_response');
  }
  return receipt;
}

async function confirmedReceipt(
  source: CapabilitySelection,
  preview: CapabilityTransfer,
  signal: AbortSignal
) {
  const endpoint = `/peers/capability-transfers/${preview.id}`;
  try {
    return parseReceipt(
      await apiClient.post<unknown>(
        `${endpoint}/send`,
        { expected_digest: preview.digest },
        { signal }
      ),
      source,
      preview
    );
  } catch (error) {
    if (signal.aborted) throw error;
    // Read once after a lost acknowledgement; never replay the installation.
    try {
      const durable = parseReceipt(
        await apiClient.get<unknown>(endpoint, { signal }),
        source,
        preview
      );
      if (durable.status !== 'preparing') return durable;
    } catch {
      /* Preserve the original failure when no authoritative receipt was read. */
    }
    throw error;
  }
}

/** Account/source lifetimes fence callbacks as well as late network results. */
export function useCapabilityTransfer(source: CapabilitySelection) {
  const { user } = useAuth();
  const { lifetime, isCurrent } = useApplicationAccountLifetime(user?.id);
  const scope = useMemo(
    () => ({ lifetime, id: source.id, kind: source.kind }),
    [lifetime, source.id, source.kind]
  );
  const active = useRef<object | null>(scope);
  const operation = useRef<Operation | null>(null);
  const previewRef = useRef<Scoped<CapabilityTransfer> | null>(null);
  const outcomeRef = useRef<Scoped<CapabilityTransfer> | null>(null);
  const key = useRef<Scoped<{ peer: string; id: string }> | null>(null);
  const [saved, save] = useState<Scoped<State>>({ scope, value: INITIAL });
  const state = saved.scope === scope ? saved.value : INITIAL;

  useEffect(() => {
    active.current = scope;
    return () => {
      if (active.current === scope) active.current = null;
      if (operation.current?.scope === scope) {
        operation.current.controller.abort();
        operation.current = null;
      }
      if (previewRef.current?.scope === scope) previewRef.current = null;
      if (outcomeRef.current?.scope === scope) outcomeRef.current = null;
      if (key.current?.scope === scope) key.current = null;
    };
  }, [scope]);

  const current = useCallback(() => active.current === scope && isCurrent(), [scope, isCurrent]);
  const accept = useCallback(
    (values: Partial<State>) => {
      if (current())
        save(previous => ({
          scope,
          value: { ...(previous.scope === scope ? previous.value : INITIAL), ...values },
        }));
    },
    [current, scope]
  );
  const run = useCallback(
    async (perform: (signal: AbortSignal) => Promise<Result>) => {
      if (!current() || operation.current) return;
      const pending: Operation = { scope, token: Symbol(), controller: new AbortController() };
      operation.current = pending;
      accept({ pending: true, error: null });
      try {
        const result = await perform(pending.controller.signal);
        if (!current() || operation.current?.token !== pending.token) return;
        if (result.type === 'preview') {
          previewRef.current = { scope, value: result.value };
          outcomeRef.current = null;
          accept({ preview: result.value, outcome: null });
        } else {
          outcomeRef.current = { scope, value: result.value };
          accept({ outcome: result.value });
        }
      } catch (error) {
        if (
          current() &&
          operation.current?.token === pending.token &&
          !pending.controller.signal.aborted
        ) {
          accept({ error: error instanceof Error ? error : new Error('capability_share.failed') });
        }
      } finally {
        if (operation.current?.token === pending.token) {
          operation.current = null;
          accept({ pending: false });
        }
      }
    },
    [accept, current, scope]
  );

  const prepare = useCallback(
    async (connectionId: string) => {
      if (!current() || operation.current) return;
      if (key.current?.scope !== scope || key.current.value.peer !== connectionId) {
        key.current = { scope, value: { peer: connectionId, id: crypto.randomUUID() } };
      }
      const idempotencyKey = key.current.value.id;
      await run(async signal => ({
        type: 'preview',
        value: parseReceipt(
          await apiClient.post<unknown>(
            '/peers/capability-transfers/preview',
            {
              connection_id: connectionId,
              kind: source.kind,
              source_id: source.id,
              idempotency_key: idempotencyKey,
            },
            { signal }
          ),
          source
        ),
      }));
    },
    [current, run, scope, source]
  );

  const matches = useCallback(
    (preview: CapabilityTransfer) =>
      current() &&
      previewRef.current?.scope === scope &&
      previewRef.current.value.id === preview.id &&
      previewRef.current.value.digest === preview.digest,
    [current, scope]
  );
  const send = useCallback(
    async (preview: CapabilityTransfer) => {
      if (!matches(preview)) return;
      const status = outcomeRef.current?.scope === scope ? outcomeRef.current.value.status : null;
      if (status && ['installed', 'installing', 'cancelled'].includes(status)) return;
      await run(async signal => ({
        type: 'outcome',
        value: await confirmedReceipt(source, preview, signal),
      }));
    },
    [matches, run, scope, source]
  );
  const refresh = useCallback(
    async (preview: CapabilityTransfer) => {
      if (!matches(preview)) return;
      await run(async signal => ({
        type: 'outcome',
        value: parseReceipt(
          await apiClient.get<unknown>(`/peers/capability-transfers/${preview.id}`, { signal }),
          source,
          preview
        ),
      }));
    },
    [matches, run, source]
  );
  const reset = useCallback(() => {
    if (!current()) return;
    operation.current?.controller.abort();
    operation.current = null;
    previewRef.current = null;
    outcomeRef.current = null;
    key.current = null;
    accept(INITIAL);
  }, [accept, current]);
  return { ...state, prepare, send, refresh, reset };
}
