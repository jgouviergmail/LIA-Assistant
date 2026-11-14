/** Every transport control names the same public discussion generation. */
import { afterEach, expect, it, vi } from 'vitest';
import { ChatSSEClient, cancelActiveRun, fetchActiveRun, fetchPendingHitl } from '../chat';
import type { ConversationSelection } from '@/types/conversation';

const selection: ConversationSelection = { conversation_id: 'annex', conversation_revision: 4 };
afterEach(() => vi.unstubAllGlobals());

it('scopes status, cancellation, pending HITL and replay to the selected generation', async () => {
  const calls: string[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      calls.push(String(url));
      return new Response('{}', { headers: { 'content-type': 'application/json' } });
    })
  );
  await fetchActiveRun(selection);
  await cancelActiveRun(selection);
  await fetchPendingHitl(undefined, selection);
  await new ChatSSEClient().reattachStream(
    'stream',
    vi.fn(),
    vi.fn(),
    vi.fn(),
    undefined,
    selection
  );
  expect(calls).toHaveLength(4);
  for (const call of calls) {
    const url = new URL(call, 'http://local');
    expect(url.searchParams.get('conversation_id')).toBe('annex');
    expect(url.searchParams.get('conversation_revision')).toBe('4');
  }
});
