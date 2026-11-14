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
import { makeTicket } from '@/__tests__/factories';

function ticket(overrides: Partial<TicketRow> & { id: string }): TicketRow {
  return makeTicket({ title: overrides.id, ...overrides });
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
    lanes: [],
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
      page: { tickets: [ticket({ id: 'a' })], total: 87, counts_by_status: { todo: 87 }, lanes: [] },
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
        lanes: [],
      },
    });

    expect(column(state, 'todo')).toEqual(['ccc', 'aaa', 'bbb']);
  });

  it('gives an unknown column an empty list rather than undefined', () => {
    expect(ticketsOf(loadedBoard(), 'idea')).toEqual([]);
  });
});

/**
 * A board with lanes: `a` and `z` filed under « home », `b` filed under
 * nothing, « work » empty. The lane counters are the server's, like the
 * column counters above.
 */
function lanedBoard(): WorkboardState {
  const page: BoardPage = {
    tickets: [
      ticket({ id: 'a', status: 'todo', position: 0, category_id: 'home' }),
      ticket({ id: 'b', status: 'todo', position: 1 }),
      ticket({ id: 'z', status: 'done', position: 0, category_id: 'home' }),
    ],
    total: 3,
    counts_by_status: { todo: 2, done: 1 },
    lanes: [
      { category_id: null, name: null, owner_user_id: null, counts_by_status: { todo: 1, done: 0 } },
      {
        category_id: 'home',
        name: 'Home',
        owner_user_id: 'owner',
        counts_by_status: { todo: 1, done: 1 },
      },
      {
        category_id: 'work',
        name: 'Work',
        owner_user_id: 'owner',
        counts_by_status: { todo: 0, done: 0 },
      },
    ],
  };
  return workboardReducer(initialWorkboardState, { type: 'loaded', page });
}

/** One lane's counters, by its category. */
function lane(state: WorkboardState, category: string | null): Record<string, number> {
  const found = state.lanes.find(row => row.category_id === category);
  if (!found) throw new Error(`no lane ${category}`);
  return found.counts_by_status;
}

describe('lanes — loaded', () => {
  it('takes the lanes and their EXACT counters from the server', () => {
    const state = lanedBoard();

    expect(state.lanes.map(row => row.category_id)).toEqual([null, 'home', 'work']);
    expect(lane(state, 'home')).toEqual({ todo: 1, done: 1 });
  });

  it('is a flat board when the answer carries no lane at all', () => {
    // An API that predates the lanes — a deploy in progress, a cached page —
    // answers without the field: the board must draw what it always drew
    // rather than crash on a list it was promised.
    const older: BoardPage = JSON.parse(
      JSON.stringify({ tickets: [], total: 0, counts_by_status: {} })
    );

    const state = workboardReducer(lanedBoard(), { type: 'loaded', page: older });

    expect(state.lanes).toEqual([]);
  });
});

describe('lanes — moved', () => {
  it('a drop in another lane files the row and moves one card between two counters', () => {
    const next = workboardReducer(lanedBoard(), {
      type: 'moved',
      id: 'b',
      status: 'todo',
      position: 0,
      lane: 'work',
    });

    expect(next.tickets.find(row => row.id === 'b')?.category_id).toBe('work');
    expect(lane(next, null).todo).toBe(0);
    expect(lane(next, 'work').todo).toBe(1);
    expect(next.countsByStatus.todo).toBe(2);
  });

  it('a drop across a lane AND a column moves the right cell on both sides', () => {
    const next = workboardReducer(lanedBoard(), {
      type: 'moved',
      id: 'a',
      status: 'done',
      position: 0,
      lane: null,
    });

    expect(next.tickets.find(row => row.id === 'a')?.category_id).toBeNull();
    expect(lane(next, 'home')).toEqual({ todo: 0, done: 1 });
    expect(lane(next, null)).toEqual({ todo: 1, done: 1 });
    expect(next.countsByStatus).toMatchObject({ todo: 1, done: 2 });
  });

  it('a column change inside one lane moves that lane’s own counters', () => {
    const next = workboardReducer(lanedBoard(), {
      type: 'moved',
      id: 'a',
      status: 'done',
      position: 0,
    });

    expect(next.tickets.find(row => row.id === 'a')?.category_id).toBe('home');
    expect(lane(next, 'home')).toEqual({ todo: 0, done: 2 });
    expect(lane(next, null)).toEqual({ todo: 1, done: 0 });
  });

  it('a reorder that names no lane touches no lane counter', () => {
    const before = lanedBoard();

    const next = workboardReducer(before, { type: 'moved', id: 'b', status: 'todo', position: 0 });

    expect(next.lanes).toEqual(before.lanes);
  });

  it('never drives a lane counter below zero, whatever the payload says', () => {
    const state = lanedBoard();
    const drifted: WorkboardState = {
      ...state,
      lanes: state.lanes.map(row =>
        row.category_id === 'home' ? { ...row, counts_by_status: { todo: 0, done: 0 } } : row
      ),
    };

    const next = workboardReducer(drifted, {
      type: 'moved',
      id: 'a',
      status: 'todo',
      position: 0,
      lane: 'work',
    });

    expect(lane(next, 'home').todo).toBe(0);
  });

  it('never mutates the lanes it was given', () => {
    const before = lanedBoard();
    const frozen = JSON.stringify(before.lanes);

    workboardReducer(before, { type: 'moved', id: 'a', status: 'done', position: 0, lane: 'work' });

    expect(JSON.stringify(before.lanes)).toBe(frozen);
  });
});

describe('lanes — restored and patched', () => {
  it('a rollback puts the lanes back EXACTLY as they were', () => {
    const before = lanedBoard();
    const moved = workboardReducer(before, {
      type: 'moved',
      id: 'a',
      status: 'done',
      position: 0,
      lane: 'work',
    });

    const restored = workboardReducer(moved, { type: 'restored', snapshot: before });

    expect(restored.lanes).toEqual(before.lanes);
    expect(restored.tickets).toEqual(before.tickets);
  });

  it('a patch that refiles the row moves the lane counters as a drop does', () => {
    const state = lanedBoard();
    const row = state.tickets.find(candidate => candidate.id === 'b');
    if (!row) throw new Error('fixture lost its row');

    const next = workboardReducer(state, {
      type: 'patched',
      ticket: { ...row, category_id: 'home' },
    });

    expect(lane(next, null).todo).toBe(0);
    expect(lane(next, 'home').todo).toBe(2);
  });

  it('a patch that changes nothing about the lane leaves the counters alone', () => {
    const state = lanedBoard();
    const row = state.tickets.find(candidate => candidate.id === 'a');
    if (!row) throw new Error('fixture lost its row');

    const next = workboardReducer(state, { type: 'patched', ticket: { ...row, title: 'Renamed' } });

    expect(next.lanes).toEqual(state.lanes);
  });
});
