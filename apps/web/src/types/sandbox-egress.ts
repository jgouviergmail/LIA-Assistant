/**
 * Wire shapes of the sandbox egress settings (ADR-298).
 *
 * Mirrors `python_sandbox/egress/schemas.py`: what a script may reach without
 * asking, and the permissions the person gave when asked.
 */

/** Where a reachable host's permission comes from. */
export type ReachableHostStatus = 'connector' | 'operator';

export interface ReachableHost {
  host: string;
  status: ReachableHostStatus;
  /** The connector whose key a script may use on this host (connector hosts only). */
  connector: string | null;
}

export interface ReachableHostsResponse {
  items: ReachableHost[];
  /** Whether an unknown host is asked of the person (else refused before the run). */
  ask_enabled: boolean;
}

export interface EgressGrant {
  id: string;
  host: string;
  /** Whether the turn's collected data may reach a script that declares this host. */
  share_turn_data: boolean;
  created_at: string;
  last_used_at: string | null;
}

export interface EgressGrantListResponse {
  items: EgressGrant[];
  /** EXACT count over the account's grants (ADR-185). */
  total: number;
  limit: number;
  offset: number;
  /** Largest page the API serves — published because it is enforced (ADR-184). */
  max_limit: number;
  /** How many grants the account may keep; past it an approval holds for its run only. */
  max_per_user: number;
}
