'use client';

/**
 * useChainSeal — what is sealed, and (on demand) whether it holds (ADR-263, lot 5).
 *
 * Two calls, deliberately, because they are two different claims:
 *
 * - the **status** is fetched on mount. It costs three indexed queries and it
 *   asserts nothing: how many entries seal the journals, up to when, and how
 *   many rows are not sealed yet.
 * - the **verdict** is fetched only when the reader asks. It walks the chain
 *   and re-digests every row it covers — the only answer that can honestly say
 *   « intact », and far too expensive to run on every page view.
 *
 * Merging them would mean either running an audit nobody asked for, or showing
 * a reassurance nothing checked. Both are the failure this whole mechanism
 * exists to remove.
 */

import { useCallback, useState } from 'react';

import { useApiQuery } from '@/hooks/useApiQuery';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';

/** What the registers' sealing looks like, without checking it. */
export interface ChainSeal {
  /** Whether this instance seals at all — « nothing sealed » is otherwise ambiguous. */
  sealing_enabled: boolean;
  /** Links the chain holds. */
  entries: number;
  /** Moment of the last link; nothing after it is sealed. */
  sealed_until: string | null;
  /** Register rows not sealed yet. */
  pending: number;
}

/** The verdict of an actual walk. */
export interface ChainVerdict {
  ok: boolean;
  entries: number;
  sealed_until: string | null;
  pending: number;
  payloads_checked: number;
  payloads_skipped: number;
  head_hash: string | null;
  broken_at_seq: number | null;
  reason: string | null;
}

export interface UseChainSealResult {
  /** The seal, `undefined` before the first payload. */
  seal: ChainSeal | undefined;
  /** The verdict, `undefined` until the reader asks for one. */
  verdict: ChainVerdict | undefined;
  loading: boolean;
  /** True while a verification is running. */
  verifying: boolean;
  error: Error | null;
  /** Run the deep verification. */
  verify: () => Promise<void>;
}

/**
 * Read the sealing state, and verify it on demand.
 */
export function useChainSeal(): UseChainSealResult {
  const { data, loading, error } = useApiQuery<ChainSeal>('/effects/chain/status', {
    componentName: 'useChainSeal',
  });
  const [verdict, setVerdict] = useState<ChainVerdict | undefined>(undefined);
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState<Error | null>(null);

  const verify = useCallback(async () => {
    setVerifying(true);
    setVerifyError(null);
    try {
      setVerdict(await apiClient.get<ChainVerdict>('/effects/chain/verify'));
    } catch (caught) {
      // The verdict is withheld rather than assumed: leaving a stale « intact »
      // on screen after a failed check would be the one lie this surface exists
      // to prevent.
      setVerdict(undefined);
      const failure = caught instanceof Error ? caught : new Error(String(caught));
      setVerifyError(failure);
      logger.error('useChainSeal: verification failed', failure);
    } finally {
      setVerifying(false);
    }
  }, []);

  return {
    seal: data ?? undefined,
    verdict,
    loading,
    verifying,
    error: verifyError ?? error,
    verify,
  };
}
