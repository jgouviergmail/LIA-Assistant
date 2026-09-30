'use client';

/**
 * useSandboxEgress — what a script or a skill's command may reach without
 * asking, and the permissions the person gave (ADR-298, ADR-327 lot 3).
 *
 * Two reads, one page each: `/sandbox/egress-grants/reachable` (connector and
 * operator hosts) and `/sandbox/egress-grants` (the grants, newest first, with
 * the EXACT total and the cap the instance enforces). Edits are optimistic
 * with a rollback, the OpenLoops doctrine: the person sees their change at
 * once and the server's row wins on the next fetch. A host allowed by hand is
 * NOT optimistic: the server normalises it and may refuse it, so the grants
 * are read again once it answers.
 */

import { useCallback, useState } from 'react';

import { ApiError } from '@/lib/api-client';
import { getApiErrorFields } from '@/lib/api-error';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';
import type {
  EgressGrant,
  EgressGrantListResponse,
  ReachableHost,
  ReachableHostsResponse,
} from '@/types/sandbox-egress';

/**
 * The grants page the section reads. The cap on grants per account (50 by
 * default) is also the largest page the API serves, so one page normally holds
 * every grant; when it does not, the exact total says so and the section
 * states the cut (ADR-185).
 */
export const GRANTS_PAGE_SIZE = 50;

export const GRANTS_PATH = `/sandbox/egress-grants?limit=${GRANTS_PAGE_SIZE}&offset=0`;
export const REACHABLE_PATH = '/sandbox/egress-grants/reachable';

/**
 * The refusals the API names when a host is allowed by hand (`detail.code`),
 * each with its sentence under `settings.sandbox_egress.add_errors` — a
 * backend guard holds the pair (`test_router.py`).
 */
export const GRANT_REFUSAL_CODES: ReadonlySet<string> = new Set([
  'egress_grant_host_invalid',
  'egress_grant_limit_reached',
  'egress_grant_asking_disabled',
]);

/**
 * What allowing a host answered: the host as the server stored it, or the
 * refusal's code when the API named one.
 */
export type AddGrantResult = { ok: true; host: string } | { ok: false; code: string | null };

/** The grants as the person sees them: this session's revokes and scope edits applied. */
export function applyOverrides(
  items: readonly EgressGrant[],
  revokedIds: ReadonlySet<string>,
  scopes: Readonly<Record<string, boolean>>
): EgressGrant[] {
  return items
    .filter(grant => !revokedIds.has(grant.id))
    .map(grant => (grant.id in scopes ? { ...grant, share_turn_data: scopes[grant.id] } : grant));
}

/**
 * The server's exact total minus what this session revoked and the server has
 * not re-counted yet — never the page length.
 */
export function exactTotal(
  page: EgressGrantListResponse | null,
  revokedIds: ReadonlySet<string>
): number {
  if (!page) return 0;
  const revokedOnPage = page.items.filter(g => revokedIds.has(g.id)).length;
  return Math.max(0, page.total - revokedOnPage);
}

/** How the two reads failed, if they did: gone (404) beats a transient failure. */
export function readFailure(errors: ReadonlyArray<Error | null>): 'unavailable' | 'error' | null {
  if (errors.some(error => error instanceof ApiError && error.status === 404)) return 'unavailable';
  if (errors.some(error => error !== null)) return 'error';
  return null;
}

export interface UseSandboxEgressReturn {
  reachable: ReachableHost[];
  /** Whether an unknown host is asked of the person; null until the answer lands. */
  askEnabled: boolean | null;
  grants: EgressGrant[];
  /** EXACT number of grants the account holds (never the page length). */
  total: number;
  maxPerUser: number;
  loading: boolean;
  /** The instance does not serve the surface (404): render nothing. */
  unavailable: boolean;
  /** A transient failure on either read: offer a retry. */
  loadError: boolean;
  refetch: () => void;
  setScope: (id: string, shareTurnData: boolean) => Promise<boolean>;
  revoke: (id: string) => Promise<boolean>;
  /** Allow a host from the settings — where no question can be asked. */
  add: (host: string, shareTurnData: boolean) => Promise<AddGrantResult>;
}

export function useSandboxEgress(enabled = true): UseSandboxEgressReturn {
  const reachableQuery = useApiQuery<ReachableHostsResponse>(REACHABLE_PATH, {
    componentName: 'useSandboxEgress',
    enabled,
  });
  const grantsQuery = useApiQuery<EgressGrantListResponse>(GRANTS_PATH, {
    componentName: 'useSandboxEgress',
    enabled,
  });

  // Optimistic overrides — derived-with-override, no sync effect.
  const [revokedIds, setRevokedIds] = useState<ReadonlySet<string>>(new Set());
  const [scopes, setScopes] = useState<Readonly<Record<string, boolean>>>({});

  const page = grantsQuery.data ?? null;
  const grants = applyOverrides(page?.items ?? [], revokedIds, scopes);
  const total = exactTotal(page, revokedIds);

  const { mutate: patchScope } = useApiMutation<{ share_turn_data: boolean }, EgressGrant>({
    method: 'PATCH',
    componentName: 'useSandboxEgress',
  });
  const { mutate: deleteGrant } = useApiMutation<undefined, undefined>({
    method: 'DELETE',
    componentName: 'useSandboxEgress',
  });
  const { mutate: postGrant } = useApiMutation<
    { host: string; share_turn_data: boolean },
    EgressGrant
  >({
    method: 'POST',
    componentName: 'useSandboxEgress',
  });

  const setScope = useCallback(
    async (id: string, shareTurnData: boolean): Promise<boolean> => {
      setScopes(prev => ({ ...prev, [id]: shareTurnData }));
      try {
        await patchScope(`/sandbox/egress-grants/${id}`, { share_turn_data: shareTurnData });
        return true;
      } catch {
        setScopes(prev => {
          const next = { ...prev };
          delete next[id];
          return next;
        });
        return false;
      }
    },
    [patchScope]
  );

  const revoke = useCallback(
    async (id: string): Promise<boolean> => {
      setRevokedIds(prev => new Set([...prev, id]));
      try {
        await deleteGrant(`/sandbox/egress-grants/${id}`);
        return true;
      } catch {
        setRevokedIds(prev => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
        return false;
      }
    },
    [deleteGrant]
  );

  // The two `refetch`s are stable (useApiQuery); the query objects are not.
  const { refetch: refetchReachable } = reachableQuery;
  const { refetch: refetchGrants } = grantsQuery;

  const add = useCallback(
    async (host: string, shareTurnData: boolean): Promise<AddGrantResult> => {
      let stored: EgressGrant | undefined;
      try {
        stored = await postGrant('/sandbox/egress-grants', {
          host,
          share_turn_data: shareTurnData,
        });
      } catch (error) {
        const code = getApiErrorFields(error)?.code;
        return {
          ok: false,
          code: typeof code === 'string' && GRANT_REFUSAL_CODES.has(code) ? code : null,
        };
      }
      // The stored row wins over a scope toggled earlier in this session: a
      // host allowed again takes the scope the server just wrote.
      const storedId = stored?.id;
      if (storedId) {
        setScopes(prev => {
          if (!(storedId in prev)) return prev;
          const next = { ...prev };
          delete next[storedId];
          return next;
        });
      }
      void refetchGrants();
      // The server normalises the name: say what it stored, as the list will.
      return { ok: true, host: stored?.host ?? host };
    },
    [postGrant, refetchGrants]
  );
  const refetch = useCallback(() => {
    setRevokedIds(new Set());
    setScopes({});
    void refetchReachable();
    void refetchGrants();
  }, [refetchReachable, refetchGrants]);

  const failure = readFailure([reachableQuery.error, grantsQuery.error]);
  const reachable = reachableQuery.data ?? null;

  return {
    reachable: reachable?.items ?? [],
    askEnabled: reachable ? reachable.ask_enabled : null,
    grants,
    total,
    maxPerUser: page?.max_per_user ?? 0,
    loading: reachableQuery.loading || grantsQuery.loading,
    unavailable: failure === 'unavailable',
    loadError: failure === 'error',
    refetch,
    setScope,
    revoke,
    add,
  };
}
