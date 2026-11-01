'use client';

import type { TFunction } from 'i18next';

import { useMCPServerBehavior } from '@/hooks/useMCPServerBehavior';
import { useMCPToolChoiceFlow } from '@/hooks/useMCPToolChoiceFlow';
import { MCPConfirmationLooseningDialog } from './MCPConfirmationLooseningDialog';
import { MCPServerBehaviorPanel } from './MCPServerBehaviorPanel';

interface Props {
  serverId: string;
  ownerId: string | undefined;
  t: TFunction;
}

/**
 * What a saved server will do, with a choice for each of its tools (spec 2026-10-30 D6).
 *
 * The person's own page only: a choice that makes LIA ask less is listed before it
 * applies (§ 6), and the synthesis is read again once a choice is written. Mount it
 * keyed by the server, like the read-only view.
 */
export function MCPServerBehaviorEditor({ serverId, ownerId, t }: Props) {
  const { behavior, loading, error, refetch } = useMCPServerBehavior(serverId);
  const flow = useMCPToolChoiceFlow(serverId, ownerId, () => void refetch(), t);
  return (
    <>
      <MCPServerBehaviorPanel
        behavior={behavior}
        loading={loading}
        updating={flow.busy}
        notice={error && !behavior ? t('settings.mcp.behavior.load_failed') : null}
        onToolChoice={(tool, choice) => void flow.choose(tool.tool_name, choice)}
        t={t}
      />
      <MCPConfirmationLooseningDialog
        losses={flow.pending?.losses ?? null}
        onCancel={flow.cancel}
        onConfirm={() => void flow.confirm()}
        t={t}
      />
    </>
  );
}
