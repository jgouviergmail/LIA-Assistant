/**
 * `useWaitingMessage` — the discussion's message that waits for its turn (ADR-384).
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

import { useWaitingMessage } from '../useWaitingMessage';
import type { WaitingMessage } from '@/lib/waiting-message';

const mockApi = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}));

vi.mock('@/lib/api-client', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api-client')>('@/lib/api-client');
  return { ...actual, default: mockApi, apiClient: mockApi };
});

afterEach(() => vi.clearAllMocks());

const SELECTION = { conversation_id: 'c1', conversation_revision: 2 };
const QUERY = '?conversation_id=c1&conversation_revision=2';

function waiting(overrides: Partial<WaitingMessage> = {}): WaitingMessage {
  return {
    conversation_id: 'c1',
    conversation_revision: 2,
    content: 'And the bakery',
    status: 'waiting',
    version: 1,
    send_requested: false,
    stream_id: null,
    can_join: false,
    created_at: '2026-11-13T15:00:00Z',
    updated_at: '2026-11-13T15:00:00Z',
    ...overrides,
  };
}

async function mounted(initial: WaitingMessage | null) {
  mockApi.get.mockResolvedValueOnce(initial);
  const hook = renderHook(() => useWaitingMessage(SELECTION, true));
  await waitFor(() => expect(mockApi.get).toHaveBeenCalled());
  await waitFor(() => expect(hook.result.current.message).toEqual(initial));
  return hook;
}

describe('useWaitingMessage', () => {
  it('reads the selected discussion’s waiting message', async () => {
    await mounted(waiting());
    expect(mockApi.get).toHaveBeenCalledWith(
      '/agents/chat/waiting',
      expect.objectContaining({ params: SELECTION })
    );
  });

  it('reads nothing while disabled', async () => {
    renderHook(() => useWaitingMessage(SELECTION, false));
    await Promise.resolve();
    expect(mockApi.get).not.toHaveBeenCalled();
  });

  it('keeps words behind the running answer and shows what waits', async () => {
    const { result } = await mounted(null);
    const kept = waiting({ content: 'Add the dentist' });
    mockApi.post.mockResolvedValueOnce({ waiting: kept, departed: false, stream_id: null });
    let response: Awaited<ReturnType<typeof result.current.queue>> | undefined;
    await act(async () => {
      response = await result.current.queue('Add the dentist', {
        behindStreamId: 'run-1',
        rendering: { viewport_width: 390 },
      });
    });
    expect(mockApi.post).toHaveBeenCalledWith(
      `/agents/chat/waiting${QUERY}`,
      { message: 'Add the dentist', behind_stream_id: 'run-1', rendering: { viewport_width: 390 } },
      undefined
    );
    expect(response?.departed).toBe(false);
    expect(result.current.message).toEqual(kept);
  });

  it('shows nothing once the words left at once', async () => {
    const { result } = await mounted(waiting({ status: 'held' }));
    mockApi.post.mockResolvedValueOnce({ waiting: null, departed: true, stream_id: 'run-2' });
    await act(async () => {
      await result.current.queue('Send it all', { behindStreamId: null });
    });
    expect(mockApi.post.mock.calls[0][1]).toEqual({ message: 'Send it all' });
    expect(result.current.message).toBeNull();
  });

  it('leaves what waits untouched when the server refuses the words', async () => {
    const shown = waiting();
    const { result } = await mounted(shown);
    mockApi.post.mockRejectedValueOnce(new Error('too long'));
    await act(async () => {
      await expect(result.current.queue('x', { behindStreamId: null })).rejects.toThrow('too long');
    });
    expect(result.current.message).toEqual(shown);
  });

  it('edits the version on screen', async () => {
    const { result } = await mounted(waiting({ version: 3 }));
    const edited = waiting({ content: 'The bakery only', version: 4 });
    mockApi.put.mockResolvedValueOnce(edited);
    await act(async () => {
      await result.current.edit('The bakery only');
    });
    expect(mockApi.put).toHaveBeenCalledWith(
      `/agents/chat/waiting${QUERY}`,
      { message: 'The bakery only', version: 3 },
      undefined
    );
    expect(result.current.message).toEqual(edited);
  });

  it('withdraws the message', async () => {
    const { result } = await mounted(waiting());
    mockApi.delete.mockResolvedValueOnce(undefined);
    await act(async () => {
      await result.current.withdraw();
    });
    expect(mockApi.delete).toHaveBeenCalledWith(
      `/agents/chat/waiting${QUERY}`,
      expect.objectContaining({ body: undefined })
    );
    expect(result.current.message).toBeNull();
  });

  it('asks to send now, then reads where the message stands', async () => {
    const { result } = await mounted(waiting());
    mockApi.post.mockResolvedValueOnce({ departed: false, stopping: true, stream_id: null });
    mockApi.get.mockResolvedValueOnce(waiting({ send_requested: true }));
    let response: Awaited<ReturnType<typeof result.current.sendNow>> | undefined;
    await act(async () => {
      response = await result.current.sendNow();
    });
    expect(mockApi.post).toHaveBeenCalledWith(`/agents/chat/waiting/send${QUERY}`, undefined, undefined);
    expect(response?.stopping).toBe(true);
    await waitFor(() => expect(result.current.message?.send_requested).toBe(true));
  });

  it('joins the answer being written with the version on screen (ADR-385)', async () => {
    const { result } = await mounted(waiting({ version: 2, can_join: true }));
    const joined = waiting({ version: 2, status: 'joining', stream_id: 'run-1' });
    mockApi.post.mockResolvedValueOnce(joined);
    await act(async () => {
      await result.current.join();
    });
    expect(mockApi.post).toHaveBeenCalledWith(
      `/agents/chat/waiting/join${QUERY}`,
      { version: 2 },
      undefined
    );
    expect(result.current.message).toEqual(joined);
  });

  it('leaves the message as it was when the answer took no note', async () => {
    const shown = waiting({ can_join: true });
    const { result } = await mounted(shown);
    mockApi.post.mockRejectedValueOnce(new Error('closed'));
    await act(async () => {
      await expect(result.current.join()).rejects.toThrow('closed');
    });
    expect(result.current.message).toEqual(shown);
  });

  it('joins nothing when nothing waits', async () => {
    const { result } = await mounted(null);
    await act(async () => {
      expect(await result.current.join()).toBeUndefined();
    });
    expect(mockApi.post).not.toHaveBeenCalled();
  });
});
