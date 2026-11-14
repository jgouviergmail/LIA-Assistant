'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { ConversationTotals } from '@/hooks/useConversation';
import type { ConversationTotalsDisplay } from '@/components/chat/ContextUsagePill';

function displayTotals(totals: ConversationTotals | null): ConversationTotalsDisplay | null {
  if (!totals || !Number.isFinite(totals.total_cost_eur)) return null;
  return {
    tokensIn: totals.total_tokens_in,
    tokensOut: totals.total_tokens_out,
    tokensCache: totals.total_tokens_cache,
    costEur: totals.total_cost_eur,
    googleApiRequests: totals.total_google_api_requests,
    userMessageCount: totals.user_message_count,
  };
}

/** Rebase on one cumulative server figure. Replayed SSE deltas are never added to it. */
export function useDiscussionUsage(
  load: () => Promise<ConversationTotals | null>,
  typing: boolean,
  hydrateContext: (tokens: number | null | undefined, threshold: number | null | undefined) => void
) {
  const [totals, setTotals] = useState<ConversationTotals | null>(null);
  const sequence = useRef(0);
  const wasTyping = useRef(typing);
  const replace = useCallback((result: ConversationTotals | null) => {
    sequence.current += 1;
    setTotals(result);
  }, []);
  const refresh = useCallback(async () => {
    const request = ++sequence.current;
    try {
      const next = await load();
      if (sequence.current !== request || !next) return;
      setTotals(next);
      hydrateContext(next.context_tokens, next.context_threshold);
    } catch {
      // The loader reports failures. Retain the last verified measurement.
    }
  }, [hydrateContext, load]);
  useEffect(() => {
    const finished = wasTyping.current && !typing;
    wasTyping.current = typing;
    if (finished) void refresh();
  }, [refresh, typing]);
  return { totals: displayTotals(totals), replace, refresh };
}
