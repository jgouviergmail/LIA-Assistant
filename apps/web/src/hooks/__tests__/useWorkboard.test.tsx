/**
 * The board's one hook: what it reads, what it re-reads, and what it says when
 * a write is refused.
 *
 * Four properties are pinned here because each is a defect this repository has
 * already paid for once:
 *
 * - a REFRESH is not a first load (`PeerConnectionsSettings`, 2026-07-31): the
 *   spinner flag is derived from the ABSENCE of data, never from `error`,
 *   which a refetch clears;
 * - a refused write must reach the caller as a CODE, never as an exception the
 *   caller may forget to catch;
 * - an optimistic move that the server refuses restores the board EXACTLY,
 *   order included;
 * - a tab left open sees a peer's change on its next focus, and the listener
 *   is removed on unmount (a leak here fires against a dead component).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

import { useWorkboard } from '@/hooks/useWorkboard';
import { ApiError } from '@/lib/api-client';
import type { BoardPage, TicketRow } from '@/types/workboard';

const api = vi.hoisted(() => ({
  board: vi.fn(),
  move: vi.fn(),
  update: vi.fn(),
  create: vi.fn(),
  comment: vi.fn(),
  runNow: vi.fn(),
  remove: vi.fn(),
  detail: vi.fn(),
  needsMe: vi.fn(),
}));
vi.mock('@/lib/workboard/api', () => ({ workboardApi: api, boardParams: vi.fn(() => ({})) }));

function ticket(overrides: Partial<TicketRow> & { id: string }): TicketRow {
  return {
    owner_user_id: 'owner',
    parent_id: null,
    title: overrides.id,
    description: null,
    status: 'todo',
    priority: 'medium',
    start_at: null,
    due_at: null,
    assignee_kind: 'human',
    assignee_user_id: null,
    effective_assignee_id: 'owner',
    position: 0,
    follow_owner: false,
    follow_assignee: false,
    created_by: 'user',
    status_changed_at: '2026-09-09T10:00:00Z',
    run_count: 0,
    run_claimed_at: null,
    last_run_at: null,
    last_run_outcome: null,
    last_run_error: null,
    last_run_tokens_in: null,
    last_run_tokens_out: null,
    last_run_cost_eur: null,
    created_at: '2026-09-09T10:00:00Z',
    execution_mode: 'react',
    total_tokens_in: 0,
    total_tokens_out: 0,
    total_tokens_cache: 0,
    total_google_requests: 0,
    total_cost_eur: 0,
    updated_at: '2026-09-09T10:00:00Z',
    ...overrides,
  };
}

function page(): BoardPage {
  return {
    tickets: [
      ticket({ id: 'a', status: 'todo', position: 0 }),
      ticket({ id: 'b', status: 'todo', position: 1 }),
    ],
    total: 2,
    counts_by_status: { todo: 2, done: 0 },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.board.mockResolvedValue(page());
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('reading the board', () => {
  it('reports a first load, then never again on a refetch', async () => {
    const { result } = renderHook(() => useWorkboard());

    expect(result.current.firstLoad).toBe(true);
    await waitFor(() => expect(result.current.firstLoad).toBe(false));
    expect(result.current.total).toBe(2);

    // A refetch keeps the content mounted: `firstLoad` must stay false even
    // while the request is in flight, or the list unmounts and takes the
    // reader's place with it.
    let resolve: (value: BoardPage) => void = () => {};
    api.board.mockReturnValueOnce(new Promise<BoardPage>(done => (resolve = done)));
    act(() => void result.current.refetch());
    expect(result.current.firstLoad).toBe(false);
    await act(async () => {
      resolve(page());
    });
  });

  it('keeps the EXACT totals the server sent, never the page length', async () => {
    api.board.mockResolvedValue({
      tickets: [ticket({ id: 'a' })],
      total: 87,
      counts_by_status: { todo: 87 },
    });
    const { result } = renderHook(() => useWorkboard());

    await waitFor(() => expect(result.current.total).toBe(87));
    expect(result.current.countsByStatus.todo).toBe(87);
    expect(result.current.tickets).toHaveLength(1);
  });

  it('reads a 404 as « the feature is off », not as an error to shout about', async () => {
    api.board.mockRejectedValue(new ApiError('not found', 404));
    const { result } = renderHook(() => useWorkboard());

    await waitFor(() => expect(result.current.isUnavailable).toBe(true));
    expect(result.current.error).toBeNull();
  });

  it('surfaces any other failure as an error', async () => {
    api.board.mockRejectedValue(new ApiError('boom', 500));
    const { result } = renderHook(() => useWorkboard());

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.isUnavailable).toBe(false);
  });
});

describe('seeing what someone else changed', () => {
  it('re-reads the board when the tab comes back', async () => {
    const { result } = renderHook(() => useWorkboard());
    await waitFor(() => expect(result.current.firstLoad).toBe(false));
    expect(api.board).toHaveBeenCalledTimes(1);

    await act(async () => {
      Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });

    await waitFor(() => expect(api.board).toHaveBeenCalledTimes(2));
  });

  it('does not re-read when the tab is being HIDDEN', async () => {
    const { result } = renderHook(() => useWorkboard());
    await waitFor(() => expect(result.current.firstLoad).toBe(false));

    await act(async () => {
      Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(api.board).toHaveBeenCalledTimes(1);
  });

  it('removes its listener on unmount', async () => {
    const { result, unmount } = renderHook(() => useWorkboard());
    await waitFor(() => expect(result.current.firstLoad).toBe(false));
    unmount();

    await act(async () => {
      Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(api.board).toHaveBeenCalledTimes(1);
  });
});

describe('moving a card', () => {
  it('shows the move immediately and keeps it when the server agrees', async () => {
    api.move.mockResolvedValue(ticket({ id: 'a', status: 'done', position: 0 }));
    const { result } = renderHook(() => useWorkboard());
    await waitFor(() => expect(result.current.firstLoad).toBe(false));

    let outcome: { ok: boolean; errorCode: string | null } | undefined;
    await act(async () => {
      outcome = await result.current.move('a', 'done', 0);
    });

    expect(outcome).toEqual({ ok: true, errorCode: null });
    expect(result.current.countsByStatus.done).toBe(1);
    expect(result.current.tickets.find(row => row.id === 'a')?.status).toBe('done');
  });

  it('puts the board back EXACTLY when the server refuses', async () => {
    api.move.mockRejectedValue(
      new ApiError('refused', 400, { detail: 'workboard_status_invalid' })
    );
    const { result } = renderHook(() => useWorkboard());
    await waitFor(() => expect(result.current.firstLoad).toBe(false));
    const before = result.current.tickets.map(row => `${row.id}:${row.status}:${row.position}`);

    let outcome: { ok: boolean; errorCode: string | null } | undefined;
    await act(async () => {
      outcome = await result.current.move('a', 'done', 0);
    });

    expect(outcome).toEqual({ ok: false, errorCode: 'workboard_status_invalid' });
    expect(result.current.tickets.map(row => `${row.id}:${row.status}:${row.position}`)).toEqual(
      before
    );
    expect(result.current.countsByStatus).toEqual({ todo: 2, done: 0 });
  });
});

describe('every verb answers, and none of them throws', () => {
  it('reports a refusal as its stable code', async () => {
    api.update.mockRejectedValue(
      new ApiError('nope', 400, { detail: 'workboard_peer_cannot_edit_field' })
    );
    const { result } = renderHook(() => useWorkboard());
    await waitFor(() => expect(result.current.firstLoad).toBe(false));

    let outcome: { ok: boolean; errorCode: string | null } | undefined;
    await act(async () => {
      outcome = await result.current.patch('a', { title: 'x' });
    });

    expect(outcome).toEqual({ ok: false, errorCode: 'workboard_peer_cannot_edit_field' });
  });

  it('answers a shapeless failure with no code rather than inventing one', async () => {
    api.comment.mockRejectedValue(new Error('network'));
    const { result } = renderHook(() => useWorkboard());
    await waitFor(() => expect(result.current.firstLoad).toBe(false));

    let outcome: { ok: boolean; errorCode: string | null } | undefined;
    await act(async () => {
      outcome = await result.current.comment('a', 'hello');
    });

    expect(outcome).toEqual({ ok: false, errorCode: null });
  });

  it('re-reads the board after a creation and after a deletion', async () => {
    // Both change rows this page cannot see — a child in another column, a row
    // past the page — so the exact counts have to be re-read, never guessed.
    api.create.mockResolvedValue(ticket({ id: 'new' }));
    api.remove.mockResolvedValue({ removed: 2 });
    const { result } = renderHook(() => useWorkboard());
    await waitFor(() => expect(result.current.firstLoad).toBe(false));

    await act(async () => {
      await result.current.create({ title: 'x' });
    });
    await waitFor(() => expect(api.board).toHaveBeenCalledTimes(2));

    await act(async () => {
      await result.current.remove('a');
    });
    await waitFor(() => expect(api.board).toHaveBeenCalledTimes(3));
  });

  it('applies what the server answered after a patch, without a refetch', async () => {
    // A patch returns the row itself, so the board takes the server's word and
    // spends no request: this is the path the status `<select>` uses.
    api.update.mockResolvedValue(ticket({ id: 'a', status: 'waiting', position: 0 }));
    const { result } = renderHook(() => useWorkboard());
    await waitFor(() => expect(result.current.firstLoad).toBe(false));

    await act(async () => {
      await result.current.patch('a', { status: 'waiting' });
    });

    expect(result.current.tickets.find(row => row.id === 'a')?.status).toBe('waiting');
    expect(result.current.countsByStatus.waiting).toBe(1);
    expect(result.current.countsByStatus.todo).toBe(1);
    expect(api.board).toHaveBeenCalledTimes(1);
  });
});

describe('two moves before the first answer', () => {
  it('rolling back the refused one leaves the accepted one alone', async () => {
    // A reader dragging two cards quickly. A `move` closing over the state it
    // was BUILT with would snapshot the board as it was before BOTH moves, so
    // the second's rollback would silently undo the first.
    api.move.mockImplementation(async (id: string) => {
      if (id === 'b') throw new ApiError('refused', 400, { detail: 'workboard_status_invalid' });
      return ticket({ id: 'a', status: 'done', position: 0 });
    });
    const { result } = renderHook(() => useWorkboard());
    await waitFor(() => expect(result.current.firstLoad).toBe(false));

    await act(async () => {
      await result.current.move('a', 'done', 0);
    });
    await act(async () => {
      await result.current.move('b', 'done', 0);
    });

    // 'a' stays where the server put it; 'b' is back in its column.
    expect(result.current.tickets.find(row => row.id === 'a')?.status).toBe('done');
    expect(result.current.tickets.find(row => row.id === 'b')?.status).toBe('todo');
    expect(result.current.countsByStatus.done).toBe(1);
    expect(result.current.countsByStatus.todo).toBe(1);
  });
});

describe('re-reading itself, without impact', () => {
  // The sweep runs a ticket a minute, so the board moves while nobody touches
  // it. « Without impact » is three separate promises, and each is tested.
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  const tick = async (ms = 30_000) => {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ms);
    });
  };

  it('re-reads on its own after half a minute', async () => {
    const { result } = renderHook(() => useWorkboard());
    await waitFor(() => expect(result.current.firstLoad).toBe(false));

    await tick();

    expect(api.board).toHaveBeenCalledTimes(2);
  });

  it('never raises the busy flag: the refresh button must not spin by itself', async () => {
    const { result } = renderHook(() => useWorkboard());
    await waitFor(() => expect(result.current.firstLoad).toBe(false));

    await tick();

    expect(result.current.loading).toBe(false);
  });

  it('shows the last board the server confirmed when a poll fails', async () => {
    const { result } = renderHook(() => useWorkboard());
    await waitFor(() => expect(result.current.firstLoad).toBe(false));
    const shown = result.current.tickets.length;
    api.board.mockRejectedValueOnce(new Error('a lost second'));

    await tick();

    // A minute-old board beats an error page for something nobody asked for.
    expect(result.current.error).toBeNull();
    expect(result.current.tickets).toHaveLength(shown);
  });

  it('stands aside while a card is in the air', async () => {
    const { result } = renderHook(({ paused }) => useWorkboard({}, { paused }), {
      initialProps: { paused: true },
    });
    await waitFor(() => expect(result.current.firstLoad).toBe(false));

    await tick();

    expect(api.board).toHaveBeenCalledTimes(1);
  });

  it('reads nothing at all in a hidden tab', async () => {
    Object.defineProperty(document, 'hidden', { value: true, configurable: true });
    const { result } = renderHook(() => useWorkboard());
    await waitFor(() => expect(result.current.firstLoad).toBe(false));

    await tick();

    expect(api.board).toHaveBeenCalledTimes(1);
    Object.defineProperty(document, 'hidden', { value: false, configurable: true });
  });

  it('stops polling once unmounted', async () => {
    const { result, unmount } = renderHook(() => useWorkboard());
    await waitFor(() => expect(result.current.firstLoad).toBe(false));
    unmount();

    await tick(120_000);

    expect(api.board).toHaveBeenCalledTimes(1);
  });

  it('stands aside while a write has not answered, optimistic ones included', async () => {
    const { result } = renderHook(() => useWorkboard());
    await waitFor(() => expect(result.current.firstLoad).toBe(false));
    let land: (row: TicketRow) => void = () => {};
    api.move.mockReturnValueOnce(
      new Promise<TicketRow>(resolve => {
        land = resolve;
      })
    );
    let moving: Promise<unknown> = Promise.resolve();
    await act(async () => {
      moving = result.current.move('t1', 'done', 0);
    });

    await tick();

    // A poll answering between the move's dispatch and its confirmation would
    // paint the board the server still knows, and the card would jump back.
    expect(api.board).toHaveBeenCalledTimes(1);
    // Awaited INSIDE act: a write still running when the test ends dispatches
    // into the next one's environment.
    await act(async () => {
      land(ticket({ id: 't1', status: 'done' }));
      await moving;
    });
  });

  it('reads again once the write has answered', async () => {
    // The counter is released in a `finally`, ONCE per write: a stray second
    // increment (a half-applied edit) would leave it above zero for good, and
    // the board would never re-read itself again.
    const { result } = renderHook(() => useWorkboard());
    await waitFor(() => expect(result.current.firstLoad).toBe(false));
    api.move.mockResolvedValueOnce(ticket({ id: 't1', status: 'done' }));
    await act(async () => {
      await result.current.move('t1', 'done', 0);
    });

    await tick();

    expect(api.board).toHaveBeenCalledTimes(2);
  });

  it('releases the write even when the server refuses it', async () => {
    const { result } = renderHook(() => useWorkboard());
    await waitFor(() => expect(result.current.firstLoad).toBe(false));
    api.update.mockRejectedValueOnce(new Error('refused'));
    await act(async () => {
      await result.current.patch('t1', { title: 'x' });
    });

    await tick();

    expect(api.board).toHaveBeenCalledTimes(2);
  });
});
