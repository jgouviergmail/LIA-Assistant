import { useCallback, useEffect, useRef, useState } from 'react';

import { useMCPBehaviorPreview, useMCPServerBehavior } from './useMCPServerBehavior';
import type { MCPBehaviorCandidates, MCPServerBehavior } from '@/lib/mcp-behavior';

/** The pause after a change before the API is asked — never a request per click. */
export const MCP_PREVIEW_DELAY_MS = 300;

interface Settled {
  /** The candidates (and refresh) the answer is for. */
  key: string;
  /** The previewed synthesis; null when the preview failed. */
  behavior: MCPServerBehavior | null;
}

/**
 * What a server will do, following the form before saving (spec 2026-10-30 § 4).
 *
 * Untouched (`{}`), the stored synthesis. A change is previewed once the person
 * pauses; until its answer arrives the last synthesis stays shown, marked
 * `updating`; an answer for an older change is dropped; a failed preview shows the
 * stored synthesis and says so (`previewFailed`) rather than a guess. `refresh`
 * re-reads both after the server's catalogue moved (a connection test).
 */
export function useMCPLiveBehavior(serverId: string | null, candidates: MCPBehaviorCandidates) {
  const stored = useMCPServerBehavior(serverId);
  const { previewServer } = useMCPBehaviorPreview();
  const [version, setVersion] = useState(0);
  const [settled, setSettled] = useState<Settled | null>(null);
  const latest = useRef(candidates);
  useEffect(() => {
    latest.current = candidates;
  });

  const values = JSON.stringify(candidates);
  const active = serverId !== null && values !== '{}';
  const requestKey = `${version}:${values}`;
  // Back to the stored values: a later change starts from the stored synthesis, not
  // from an older preview (React's « adjusting state when a prop changes »).
  if (!active && settled !== null) setSettled(null);

  useEffect(() => {
    if (!active || serverId === null) return;
    let current = true;
    const timer = setTimeout(() => {
      previewServer(serverId, latest.current).then(
        result => current && setSettled({ key: requestKey, behavior: result?.behavior ?? null }),
        () => current && setSettled({ key: requestKey, behavior: null })
      );
    }, MCP_PREVIEW_DELAY_MS);
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [active, serverId, requestKey, previewServer]);

  const { refetch } = stored;
  const refresh = useCallback(() => {
    void refetch();
    setVersion(v => v + 1);
  }, [refetch]);

  const answered = active && settled?.key === requestKey;
  const behavior = (active ? settled?.behavior : null) ?? stored.behavior;
  return {
    behavior,
    // About what is SHOWN: a preview that answered is a synthesis, whatever the first read did.
    loading: stored.loading && behavior === undefined,
    loadFailed: stored.error !== null && behavior === undefined,
    updating: active && !answered,
    previewFailed: answered && settled?.behavior === null,
    refresh,
  };
}
