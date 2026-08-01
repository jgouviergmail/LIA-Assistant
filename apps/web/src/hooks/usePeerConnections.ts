/**
 * usePeerConnections — the /peers surface hook (peers program, Lot 2).
 *
 * Wraps the Lot 1 REST surface: discovery opt-in + search, request lifecycle,
 * connections with BOTH share directions, blocks and the transparency access
 * log. After every state-changing success the affected queries are refetched
 * (no manual cache surgery). Every verb resolves to a `PeerActionResult`
 * carrying the backend's stable `peers_*` code WITH the outcome (never via
 * state, which a caller reading right after `await` would see stale) — the
 * components map codes to localized toasts (label-key doctrine).
 */

import { useCallback } from 'react';

import { ApiError } from '@/lib/api-client';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';

export interface DiscoveryMatch {
  peer_id: string;
  display_name: string;
  email_hint: string;
  /** Searcher's relationship to this match — 'none' also covers declined/removed history. */
  relationship: 'none' | 'pending' | 'connected';
}

export interface ShareItem {
  domain: 'calendar' | 'task';
  level: 'availability' | 'details' | 'titles';
}

export interface ConnectionView {
  id: string;
  peer_id: string;
  peer_display_name: string;
  peer_email_hint: string;
  /** The peer's real address — present only when they opted in AND we are connected. */
  peer_email: string | null;
  status: 'pending' | 'accepted';
  direction: 'incoming' | 'outgoing' | null;
  requested_at: string;
  responded_at: string | null;
  context_message: string | null;
  my_shares: ShareItem[];
  their_shares: ShareItem[];
}

export interface BlockView {
  blocked_id: string;
  blocked_display_name: string | null;
  created_at: string;
}

export interface AccessLogEntry {
  accessor_display_name: string;
  domain: string;
  tool_name: string;
  created_at: string;
}

interface DiscoveryState {
  discovery_enabled: boolean;
  /** ADR-189: whether ACCEPTED connections see this user's real address. */
  email_visible: boolean;
}

/** Outcome of one state-changing verb — the error code travels WITH the
 * result (never through state, which a caller reading right after `await`
 * would see stale). */
export interface PeerActionResult {
  ok: boolean;
  errorCode: string | null;
}

/** Outcome of a discovery search. `matches` is null on failure. */
export interface PeerSearchResult {
  matches: DiscoveryMatch[] | null;
  errorCode: string | null;
}

/** Extract the stable `peers_*` code from an ApiError body, if any. */
function extractErrorCode(err: unknown): string | null {
  if (err instanceof ApiError && err.data && typeof err.data === 'object') {
    const detail = (err.data as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
  }
  return null;
}

/**
 * Manage the peer-connections surface.
 *
 * @param enabled - Skip all queries when false (section gated off).
 */
export function usePeerConnections(enabled = true) {

  const me = useApiQuery<DiscoveryState>('/peers/me', {
    componentName: 'usePeerConnections',
    enabled,
  });
  const requests = useApiQuery<ConnectionView[]>('/peers/requests', {
    componentName: 'usePeerConnections',
    enabled,
  });
  const connections = useApiQuery<ConnectionView[]>('/peers/connections', {
    componentName: 'usePeerConnections',
    enabled,
  });
  const blocks = useApiQuery<BlockView[]>('/peers/blocks', {
    componentName: 'usePeerConnections',
    enabled,
  });
  const accessLog = useApiQuery<AccessLogEntry[]>('/peers/access-log', {
    componentName: 'usePeerConnections',
    enabled,
  });

  const queries = [me, requests, connections, blocks, accessLog];
  const anyLoading = queries.some(query => query.loading);
  // Monotone by construction — and that is the whole point. `useApiQuery`
  // only ever SETS `data` (a refetch never clears it, and never clears it on
  // failure either), so once one query has answered this flips to false and
  // stays false. Deriving it from `error` instead would not be monotone: a
  // refetch resets `error` to null, which would resurrect the very unmount
  // this exists to prevent.
  const neverAnswered = queries.every(query => query.data === undefined);

  const postMutation = useApiMutation({ method: 'POST', componentName: 'usePeerConnections' });
  const putMutation = useApiMutation({ method: 'PUT', componentName: 'usePeerConnections' });
  const deleteMutation = useApiMutation({ method: 'DELETE', componentName: 'usePeerConnections' });

  const mutating = postMutation.loading || putMutation.loading || deleteMutation.loading;

  // Stable locals: useCallback deps must be the values actually read (React
  // Compiler preservation rule) — the container objects change every render,
  // their mutate/refetch functions do not.
  const { mutate: postMutate } = postMutation;
  const { mutate: putMutate } = putMutation;
  const { mutate: deleteMutate } = deleteMutation;
  const { refetch: refetchMe } = me;
  const { refetch: refetchRequests } = requests;
  const { refetch: refetchConnections } = connections;
  const { refetch: refetchBlocks } = blocks;
  const { refetch: refetchAccessLog } = accessLog;

  /** Run one mutation; on success refetch the given queries. */
  const run = useCallback(
    async (
      mutate: (url: string, body?: unknown) => Promise<unknown>,
      url: string,
      body: unknown,
      refetches: Array<() => void>
    ): Promise<PeerActionResult> => {
      try {
        await mutate(url, body);
        refetches.forEach(refetch => refetch());
        return { ok: true, errorCode: null };
      } catch (err) {
        return { ok: false, errorCode: extractErrorCode(err) };
      }
    },
    []
  );

  const setDiscovery = useCallback(
    (value: boolean) =>
      run(putMutate, '/peers/me', { discovery_enabled: value }, [refetchMe]),
    [run, putMutate, refetchMe]
  );

  // Sent ALONE, never alongside the other switch: the two are independent
  // consents, and echoing a stale value would let one toggle revert the other.
  const setEmailVisible = useCallback(
    (value: boolean) => run(putMutate, '/peers/me', { email_visible: value }, [refetchMe]),
    [run, putMutate, refetchMe]
  );

  const search = useCallback(
    async (query: string): Promise<PeerSearchResult> => {
      try {
        // Forwarded verbatim: whether this is a name or an address is the
        // backend's single decision (`looks_like_email`) — a second heuristic
        // here would eventually disagree with it on the same string.
        const result = await postMutate('/peers/discovery/search', { query });
        return { matches: result as DiscoveryMatch[], errorCode: null };
      } catch (err) {
        return { matches: null, errorCode: extractErrorCode(err) };
      }
    },
    [postMutate]
  );

  const sendRequest = useCallback(
    (peerId: string, contextMessage?: string) =>
      run(
        postMutate,
        '/peers/requests',
        { peer_id: peerId, context_message: contextMessage ?? null },
        [refetchRequests, refetchConnections] // crossing requests may auto-accept
      ),
    [run, postMutate, refetchRequests, refetchConnections]
  );

  const respond = useCallback(
    (connectionId: string, accept: boolean) =>
      run(postMutate, `/peers/requests/${connectionId}/respond`, { accept }, [
        refetchRequests,
        refetchConnections,
      ]),
    [run, postMutate, refetchRequests, refetchConnections]
  );

  const removeConnection = useCallback(
    (connectionId: string) =>
      run(deleteMutate, `/peers/connections/${connectionId}`, undefined, [
        refetchConnections,
      ]),
    [run, deleteMutate, refetchConnections]
  );

  const setShare = useCallback(
    (connectionId: string, domain: string, level: string | null) =>
      run(putMutate, `/peers/connections/${connectionId}/shares`, { domain, level }, [
        refetchConnections,
      ]),
    [run, putMutate, refetchConnections]
  );

  const block = useCallback(
    (peerId: string) =>
      run(postMutate, '/peers/blocks', { peer_id: peerId }, [
        refetchBlocks,
        refetchRequests,
        refetchConnections, // blocking severs any pair state
      ]),
    [run, postMutate, refetchBlocks, refetchRequests, refetchConnections]
  );

  const unblock = useCallback(
    (peerId: string) =>
      run(deleteMutate, `/peers/blocks/${peerId}`, undefined, [refetchBlocks]),
    [run, deleteMutate, refetchBlocks]
  );

  const refetchAll = useCallback(() => {
    refetchMe();
    refetchRequests();
    refetchConnections();
    refetchBlocks();
    refetchAccessLog();
  }, [refetchMe, refetchRequests, refetchConnections, refetchBlocks, refetchAccessLog]);

  return {
    discoveryEnabled: me.data?.discovery_enabled ?? null,
    emailVisible: me.data?.email_visible ?? null,
    requests: requests.data ?? [],
    connections: connections.data ?? [],
    blocks: blocks.data ?? [],
    accessLog: accessLog.data ?? [],
    loading: anyLoading,
    // The FIRST load only. A refetch (after any mutation) also raises
    // `loading`, and swapping the section for a spinner then would unmount
    // the discovery block mid-use: the typed query, the results and the
    // keyboard focus would all be lost.
    initialLoading: neverAnswered && anyLoading,
    mutating,
    setDiscovery,
    setEmailVisible,
    search,
    sendRequest,
    respond,
    removeConnection,
    setShare,
    block,
    unblock,
    refetchAll,
  };
}
