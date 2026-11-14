/**
 * `useWaitingComposer` — what the chat does with words written while LIA works (ADR-384).
 *
 * The real `useWaitingMessage` runs against a mocked API client: the oracle is
 * the requests sent and what the page is told to do.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

import { useWaitingComposer, type UseWaitingComposerArgs } from '../useWaitingComposer';
import { ApiError } from '@/lib/api-client';
import type { WaitingMessage } from '@/lib/waiting-message';

const mockApi = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() }));
const toasts = vi.hoisted(() => ({ error: vi.fn(), info: vi.fn() }));

vi.mock('@/lib/api-client', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api-client')>('@/lib/api-client');
  return { ...actual, default: mockApi, apiClient: mockApi };
});
vi.mock('sonner', () => ({ toast: toasts }));
vi.mock('@/hooks/useLiaGender', () => ({ useLiaGender: () => ({ isMale: false }) }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

const SELECTION = { conversation_id: 'c1', conversation_revision: 0 };
const ROUTE = '/agents/chat/waiting?conversation_id=c1&conversation_revision=0';

function waiting(overrides: Partial<WaitingMessage> = {}): WaitingMessage {
  return {
    conversation_id: 'c1',
    conversation_revision: 0,
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

function args(overrides: Partial<UseWaitingComposerArgs> = {}): UseWaitingComposerArgs {
  return {
    selection: SELECTION,
    enabled: true,
    busy: false,
    questionPending: false,
    runStreamId: () => 'run-1',
    joinRun: vi.fn(),
    joinRunningAnswer: vi.fn(),
    restoreText: vi.fn(),
    ...overrides,
  };
}

async function mounted(initial: WaitingMessage | null, overrides: Partial<UseWaitingComposerArgs> = {}) {
  mockApi.get.mockResolvedValue(initial);
  const props = args(overrides);
  const hook = renderHook((p: UseWaitingComposerArgs) => useWaitingComposer(p), {
    initialProps: props,
  });
  await waitFor(() => expect(mockApi.get).toHaveBeenCalled());
  await waitFor(() => expect(hook.result.current.bubble?.message ?? null).toEqual(initial));
  return { ...hook, props };
}

beforeEach(() => {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 });
});
afterEach(() => vi.clearAllMocks());

describe('useWaitingComposer', () => {
  it('keeps words written while LIA works behind the run the page streams', async () => {
    const { result } = await mounted(null, { busy: true });
    mockApi.post.mockResolvedValueOnce({ waiting: waiting(), departed: false, stream_id: null });
    let taken = false;
    act(() => {
      taken = result.current.takes('And the bakery', {});
    });
    expect(taken).toBe(true);
    await waitFor(() =>
      expect(mockApi.post).toHaveBeenCalledWith(
        ROUTE,
        {
          message: 'And the bakery',
          behind_stream_id: 'run-1',
          rendering: { lia_gender: 'female', viewport_width: 390 },
        },
        undefined
      )
    );
    await waitFor(() => expect(result.current.bubble?.message.content).toBe('And the bakery'));
  });

  it('lets a plain send go when nothing waits', async () => {
    const { result } = await mounted(null);
    expect(result.current.takes('Hello', {})).toBe(false);
    expect(mockApi.post).not.toHaveBeenCalled();
  });

  it('adds to what waits on a free account, and joins the run that sends it', async () => {
    const { result, props } = await mounted(waiting({ status: 'held' }));
    mockApi.post.mockResolvedValueOnce({ waiting: null, departed: true, stream_id: 'run-2' });
    act(() => {
      expect(result.current.takes('Send it all', {})).toBe(true);
    });
    await waitFor(() => expect(props.joinRun).toHaveBeenCalledWith('run-2'));
    expect(mockApi.post.mock.calls[0][1]).not.toHaveProperty('behind_stream_id');
    await waitFor(() => expect(result.current.bubble).toBeNull());
  });

  it('answers a pending question instead of adding to what waits', async () => {
    const { result } = await mounted(waiting(), { questionPending: true });
    expect(result.current.takes('Yes, go ahead', {})).toBe(false);
  });

  it('never keeps what only the live request carries', async () => {
    const { result } = await mounted(null, { busy: true });
    expect(result.current.takes('With a file', { attachmentIds: ['a1'] })).toBe(false);
    expect(mockApi.post).not.toHaveBeenCalled();
  });

  it('says why the server refused the words, and gives them back', async () => {
    const { result, props } = await mounted(null, { busy: true });
    mockApi.post.mockRejectedValueOnce(
      new ApiError('conflict', 409, { detail: { error: 'waiting_message_departing', message: 'Wait a moment.' } })
    );
    act(() => {
      result.current.takes('Too soon', {});
    });
    await waitFor(() => expect(toasts.error).toHaveBeenCalledWith('Wait a moment.'));
    expect(props.restoreText).toHaveBeenCalledWith('Too soon');
  });

  it('turns a busy refusal into a waiting message and watches this discussion’s answer', async () => {
    const { result, props } = await mounted(null);
    mockApi.post.mockResolvedValueOnce({ waiting: waiting(), departed: false, stream_id: null });
    const activeRun = {
      active: true,
      conversation_id: 'c1',
      conversation_revision: 0,
      conversation_kind: 'secondary' as const,
      stream_id: 'run-9',
      can_resume: true,
    };
    let taken = false;
    act(() => {
      taken = result.current.onBusyRefusal({ content: 'Quick follow-up', activeRun });
    });
    expect(taken).toBe(true);
    expect(toasts.info).toHaveBeenCalledWith('chat.waiting.queued_busy');
    expect(props.joinRun).toHaveBeenCalledWith('run-9');
    await waitFor(() =>
      expect(mockApi.post.mock.calls[0][1]).toMatchObject({
        message: 'Quick follow-up',
        behind_stream_id: 'run-9',
      })
    );
  });

  it('reads the message again when the page’s own turn ends', async () => {
    const { rerender, props } = await mounted(waiting(), { busy: true });
    const reads = mockApi.get.mock.calls.length;
    rerender({ ...props, busy: false });
    await waitFor(() => expect(mockApi.get.mock.calls.length).toBe(reads + 1));
  });

  it('adds the waiting message to the answer being written (ADR-385)', async () => {
    const { result } = await mounted(waiting({ can_join: true }), { busy: true });
    mockApi.post.mockResolvedValueOnce(waiting({ status: 'joining', stream_id: 'run-1' }));
    act(() => result.current.bubble?.onJoin());
    await waitFor(() =>
      expect(mockApi.post).toHaveBeenCalledWith(
        '/agents/chat/waiting/join?conversation_id=c1&conversation_revision=0',
        { version: 1 },
        undefined
      )
    );
    await waitFor(() => expect(result.current.bubble?.message.status).toBe('joining'));
    expect(toasts.error).not.toHaveBeenCalled();
  });

  it('says why the answer took no note, and reads where the message stands', async () => {
    const { result } = await mounted(waiting({ can_join: true }), { busy: true });
    const reads = mockApi.get.mock.calls.length;
    mockApi.post.mockRejectedValueOnce(
      new ApiError('conflict', 409, {
        detail: { error: 'waiting_note_closed', message: 'LIA is finishing its answer.' },
      })
    );
    act(() => result.current.bubble?.onJoin());
    await waitFor(() => expect(toasts.error).toHaveBeenCalledWith('LIA is finishing its answer.'));
    await waitFor(() => expect(mockApi.get.mock.calls.length).toBe(reads + 1));
  });

  it('joins what may now run when the thread changed elsewhere', async () => {
    const { result, props } = await mounted(waiting());
    const reads = mockApi.get.mock.calls.length;
    act(() => result.current.onThreadSignal());
    expect(props.joinRunningAnswer).toHaveBeenCalledOnce();
    await waitFor(() => expect(mockApi.get.mock.calls.length).toBe(reads + 1));
  });
});
