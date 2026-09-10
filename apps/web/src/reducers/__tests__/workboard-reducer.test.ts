/**
 * The board's pure state: what a move does before the server answers.
 *
 * Every case below is a way the board could lie to the reader:
 * a card that jumps to the wrong index, a column counter that drifts one at a
 * time, a rollback that restores membership but not ORDER, a move applied to a
 * card a peer deleted a second ago. None of them raises anything — they are
 * all silently wrong on screen, which is why they are pinned here rather than
 * left to a component test.
 */
import { describe, it, expect } from 'vitest';

import {
  initialWorkboardState,
  workboardReducer,
  ticketsOf,
  type WorkboardState,
} from '@/reducers/workboard-reducer';
import type { BoardPage, TicketRow } from '@/types/workboard';

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

/** A board with three cards in `todo` and one in `done`. */
function loadedBoard(): WorkboardState {
  const page: BoardPage = {
    tickets: [
      ticket({ id: 'a', status: 'todo', position: 0 }),
      ticket({ id: 'b', status: 'todo', position: 1 }),
      ticket({ id: 'c', status: 'todo', position: 2 }),
      ticket({ id: 'z', status: 'done', position: 0 }),
    ],
    total: 4,
    counts_by_status: {
      idea: 0,
      todo: 3,
      in_progress: 0,
      waiting: 0,
      validating: 0,
      done: 1,
      cancelled: 0,
    },
  };
  return workboardReducer(initialWorkboardState, { type: 'loaded', page });
}

/** The ids of one column, in board order. */
function column(state: WorkboardState, status: string): string[] {
  return ticketsOf(state, status).map(row => row.id);
}

describe('loaded', () => {
  it('takes the page and its EXACT totals from the server', () => {
    const state = loadedBoard();

    expect(state.total).toBe(4);
    expect(state.countsByStatus.todo).toBe(3);
    // The count is the server's aggregate, never the length of the page: a
    // board bigger than one page reports more than it shows.
    const capped = workboardReducer(initialWorkboardState, {
      type: 'loaded',
      page: { tickets: [ticket({ id: 'a' })], total: 87, counts_by_status: { todo: 87 } },
    });
    expect(capped.total).toBe(87);
    expect(capped.countsByStatus.todo).toBe(87);
    expect(capped.tickets).toHaveLength(1);
  });
});

describe('moved — inside one column', () => {
  it('re-orders and re-numbers without touching any counter', () => {
    const state = workboardReducer(loadedBoard(), {
      type: 'moved',
      id: 'c',
      status: 'todo',
      position: 0,
    });

    expect(column(state, 'todo')).toEqual(['c', 'a', 'b']);
    expect(ticketsOf(state, 'todo').map(row => row.position)).toEqual([0, 1, 2]);
    expect(state.countsByStatus.todo).toBe(3);
    expect(state.total).toBe(4);
  });

  it('clamps a position past the end instead of leaving a hole', () => {
    const state = workboardReducer(loadedBoard(), {
      type: 'moved',
      id: 'a',
      status: 'todo',
      position: 99,
    });

    expect(column(state, 'todo')).toEqual(['b', 'c', 'a']);
    expect(ticketsOf(state, 'todo').map(row => row.position)).toEqual([0, 1, 2]);
  });
});

describe('moved — between columns', () => {
  it('moves exactly one card from one counter to the other', () => {
    const state = workboardReducer(loadedBoard(), {
      type: 'moved',
      id: 'b',
      status: 'done',
      position: 0,
    });

    expect(column(state, 'todo')).toEqual(['a', 'c']);
    expect(column(state, 'done')).toEqual(['b', 'z']);
    expect(state.countsByStatus.todo).toBe(2);
    expect(state.countsByStatus.done).toBe(2);
    // A move is not a creation: the board still holds four tickets.
    expect(state.total).toBe(4);
  });

  it('re-numbers BOTH columns densely', () => {
    const state = workboardReducer(loadedBoard(), {
      type: 'moved',
      id: 'a',
      status: 'done',
      position: 1,
    });

    expect(ticketsOf(state, 'todo').map(row => row.position)).toEqual([0, 1]);
    expect(ticketsOf(state, 'done').map(row => row.position)).toEqual([0, 1]);
    expect(column(state, 'done')).toEqual(['z', 'a']);
  });

  it('never drives a counter below zero, whatever the payload says', () => {
    // A card the reader drags twice before the first answer arrives, or a
    // column the server reported as empty: a negative count on screen is worse
    // than a stale one.
    const state = workboardReducer(loadedBoard(), {
      type: 'moved',
      id: 'z',
      status: 'todo',
      position: 0,
    });
    const again = workboardReducer(state, { type: 'moved', id: 'z', status: 'todo', position: 0 });

    expect(again.countsByStatus.done).toBe(0);
    expect(again.countsByStatus.todo).toBe(4);
  });
});

describe('moved — what it must NOT do', () => {
  it('is a no-op for a card the board no longer holds', () => {
    // A peer deleted it a second ago and this browser has not refetched yet.
    const before = loadedBoard();
    const after = workboardReducer(before, {
      type: 'moved',
      id: 'ghost',
      status: 'done',
      position: 0,
    });

    expect(after).toBe(before);
  });

  it('never mutates the state it was given', () => {
    const before = loadedBoard();
    const positions = before.tickets.map(row => `${row.id}:${row.status}:${row.position}`);

    workboardReducer(before, { type: 'moved', id: 'a', status: 'done', position: 0 });

    expect(before.tickets.map(row => `${row.id}:${row.status}:${row.position}`)).toEqual(positions);
    expect(before.countsByStatus.todo).toBe(3);
  });
});

describe('restored — the rollback', () => {
  it('puts the board back EXACTLY as it was, order included', () => {
    // Membership is not enough: a rollback that restores the same three cards
    // in a different order is a board the reader has to re-read.
    const before = loadedBoard();
    const optimistic = workboardReducer(before, {
      type: 'moved',
      id: 'c',
      status: 'done',
      position: 0,
    });

    const rolled = workboardReducer(optimistic, { type: 'restored', snapshot: before });

    expect(rolled).toEqual(before);
    expect(column(rolled, 'todo')).toEqual(['a', 'b', 'c']);
    expect(rolled.countsByStatus).toEqual(before.countsByStatus);
  });
});

describe('patched — the server had the last word', () => {
  it('replaces the row with the server answer and keeps the order', () => {
    const state = workboardReducer(loadedBoard(), {
      type: 'patched',
      ticket: ticket({ id: 'b', status: 'todo', position: 1, priority: 'urgent' }),
    });

    expect(column(state, 'todo')).toEqual(['a', 'b', 'c']);
    expect(state.tickets.find(row => row.id === 'b')?.priority).toBe('urgent');
  });

  it('moves the counters when the patch changed the column', () => {
    // The status `<select>` on a card goes through PATCH, not through move:
    // the counters must follow it exactly as they follow a drag.
    const state = workboardReducer(loadedBoard(), {
      type: 'patched',
      ticket: ticket({ id: 'b', status: 'waiting', position: 0 }),
    });

    expect(state.countsByStatus.todo).toBe(2);
    expect(state.countsByStatus.waiting).toBe(1);
    expect(column(state, 'waiting')).toEqual(['b']);
    expect(state.total).toBe(4);
  });

  it('ignores a row the board does not hold', () => {
    const before = loadedBoard();

    expect(workboardReducer(before, { type: 'patched', ticket: ticket({ id: 'ghost' }) })).toBe(
      before
    );
  });
});

describe('ticketsOf', () => {
  it('orders a column by position, then by id so the order is total', () => {
    // Two cards at the same position (a server that has not re-numbered yet)
    // must not swap between two renders — a list whose order depends on the
    // array's incoming order flickers.
    const state = workboardReducer(initialWorkboardState, {
      type: 'loaded',
      page: {
        tickets: [
          ticket({ id: 'bbb', status: 'todo', position: 1 }),
          ticket({ id: 'aaa', status: 'todo', position: 1 }),
          ticket({ id: 'ccc', status: 'todo', position: 0 }),
        ],
        total: 3,
        counts_by_status: { todo: 3 },
      },
    });

    expect(column(state, 'todo')).toEqual(['ccc', 'aaa', 'bbb']);
  });

  it('gives an unknown column an empty list rather than undefined', () => {
    expect(ticketsOf(loadedBoard(), 'idea')).toEqual([]);
  });
});
