/** Transport ownership survives late responses and concurrent chat controllers. */
import { afterEach, expect, it, vi } from 'vitest';

import { ChatSSEClient } from '@/lib/api/chat';
import type { ChatRequest } from '@/types/chat';

const request: ChatRequest = { message: 'hello', user_id: 'owner', session_id: 'tab' };
const encoder = new TextEncoder();

function channel() {
  let streamController: ReadableStreamDefaultController<Uint8Array> | undefined;
  const body = new ReadableStream<Uint8Array>({
    start: controller => {
      streamController = controller;
    },
  });
  return {
    response: new Response(body),
    token: (content: string) =>
      streamController?.enqueue(
        encoder.encode(`data: ${JSON.stringify({ type: 'token', content })}\n\n`)
      ),
    close: () => streamController?.close(),
  };
}

afterEach(() => vi.unstubAllGlobals());

it('ignores a retired fetch even when it resolves after the next stream started', async () => {
  const late = Promise.withResolvers<Response>();
  const live = channel();
  const signals: AbortSignal[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((_url: string, init: RequestInit) => {
      if (init.signal) signals.push(init.signal);
      return signals.length === 1 ? late.promise : Promise.resolve(live.response);
    })
  );
  const client = new ChatSSEClient();
  const staleChunk = vi.fn();
  const staleError = vi.fn();
  const staleDone = vi.fn();
  const first = client.streamChat(request, staleChunk, staleError, staleDone);
  client.cancel();
  const currentChunk = vi.fn();
  const second = client.streamChat(request, currentChunk, vi.fn(), vi.fn());
  const old = channel();
  old.token('wrong discussion');
  old.close();
  late.resolve(old.response);
  await first;
  expect(staleChunk).not.toHaveBeenCalled();
  expect(staleError).not.toHaveBeenCalled();
  expect(staleDone).not.toHaveBeenCalled();
  client.cancel();
  expect(signals[1].aborted).toBe(true);
  live.close();
  await second;
  expect(currentChunk).not.toHaveBeenCalled();
});

it('cancelling one client leaves the other subscribed and receiving its own answer', async () => {
  const left = channel();
  const right = channel();
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValueOnce(left.response).mockResolvedValueOnce(right.response)
  );
  const a = new ChatSSEClient();
  const b = new ChatSSEClient();
  const gotA = vi.fn();
  const gotB = vi.fn();
  const first = a.streamChat(request, gotA, vi.fn(), vi.fn());
  const second = b.streamChat(request, gotB, vi.fn(), vi.fn());
  await Promise.resolve();
  a.cancel();
  left.token('old');
  left.close();
  right.token('right');
  right.close();
  await Promise.all([first, second]);
  expect(gotA).not.toHaveBeenCalled();
  expect(gotB).toHaveBeenCalledWith({ type: 'token', content: 'right' });
});
