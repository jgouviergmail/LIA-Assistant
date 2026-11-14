import { act, renderHook, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { useDiscussionUsage } from '../useDiscussionUsage';
import type { ConversationTotals } from '../useConversation';

function snapshot(tokens: number): ConversationTotals {
  return {
    conversation_id: 'annex', conversation_revision: 4, total_tokens_in: tokens,
    total_tokens_out: 4, total_tokens_cache: 2, total_cost_eur: tokens / 1000,
    total_google_api_requests: 0, context_tokens: tokens * 2, context_threshold: 200,
  };
}

it('uses the cumulative server measurement after the turn and discards a slower older reply', async () => {
  const older = Promise.withResolvers<ConversationTotals>();
  const load = vi.fn<() => Promise<ConversationTotals>>()
    .mockReturnValueOnce(older.promise).mockResolvedValueOnce(snapshot(70));
  const hydrate = vi.fn();
  const hook = renderHook(({ typing }) => useDiscussionUsage(load, typing, hydrate), {
    initialProps: { typing: true },
  });
  const pending = hook.result.current.refresh();
  hook.rerender({ typing: false });
  await waitFor(() => expect(hook.result.current.totals?.tokensIn).toBe(70));
  await act(async () => { older.resolve(snapshot(25)); await pending; });
  expect(hook.result.current.totals?.costEur).toBe(0.07);
  expect(hydrate.mock.calls).toEqual([[140, 200]]);
});
