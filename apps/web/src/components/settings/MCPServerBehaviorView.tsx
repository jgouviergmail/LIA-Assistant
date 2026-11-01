'use client';

import type { TFunction } from 'i18next';

import { useMCPServerBehavior } from '@/hooks/useMCPServerBehavior';
import { MCPServerBehaviorPanel } from './MCPServerBehaviorPanel';

/**
 * A saved server's synthesis, read from the API (spec 2026-10-30 D5).
 *
 * Mount it keyed by the server: a fresh read per server, never another server's
 * synthesis left on screen while the next one loads.
 */
export function MCPServerBehaviorView({ serverId, t }: { serverId: string; t: TFunction }) {
  const { behavior, loading, error } = useMCPServerBehavior(serverId);
  return (
    <MCPServerBehaviorPanel
      behavior={behavior}
      loading={loading}
      notice={error && !behavior ? t('settings.mcp.behavior.load_failed') : null}
      t={t}
    />
  );
}
