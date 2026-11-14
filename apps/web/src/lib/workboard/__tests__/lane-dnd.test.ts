/**
 * Where a dropped ticket lands on a board WITH lanes.
 *
 * A lane board has three things a card can be released over: another card, the
 * empty part of a cell (one lane of one column), and a lane's header. Each
 * case below is a drop that would otherwise write the wrong thing — a move
 * nobody asked for, a card filed under the wrong category, a card un-filed
 * because the drop named no lane, or a position that means something in the
 * cell and nothing in the column the server orders.
 *
 * Positions are the COLUMN's, never the cell's: the server keeps one order per
 * column, and a lane is a filter over it.
 */
import { describe, it, expect } from 'vitest';

import { makeTicket } from '@/__tests__/factories';
import {
  cellDroppableId,
  cellOfDroppable,
  laneDroppableId,
  laneMove,
  laneOfDroppable,
  laneSpeech,
  placeOf,
  resolveLaneDrop,
} from '@/lib/workboard/dnd';
import { UNFILED_LANE, laneViews } from '@/lib/workboard/lanes';
import type { TicketRow } from '@/types/workboard';

function ticket(
  id: string,
  status: string,
  position: number,
  category_id: string | null
): TicketRow {
  return makeTicket({ id, title: id, status, position, category_id });
}

/**
 * `todo`, in column order: h1 (home), u1 (unfiled), h2 (home), w1 (work).
 * `done`: h3 (home). `idea`: nothing.
 */
const ROWS: TicketRow[] = [
  ticket('h1', 'todo', 0, 'home'),
  ticket('u1', 'todo', 1, null),
  ticket('h2', 'todo', 2, 'home'),
  ticket('w1', 'todo', 3, 'work'),
  ticket('h3', 'done', 0, 'home'),
];
const KNOWN = new Set(['home', 'work', 'empty']);

const column = (status: string) =>
  ROWS.filter(row => row.status === status).sort((a, b) => a.position - b.position);
const find = (id: string) => ROWS.find(row => row.id === id) ?? null;
const drop = (activeId: string, overId: string | null) =>
  resolveLaneDrop(activeId, overId, column, find, KNOWN);

describe('the droppable ids of a lane board', () => {
  it('round-trip a cell and a lane, and are never mistaken for one another', () => {
    expect(cellOfDroppable(cellDroppableId('home', 'in_progress'))).toEqual({
      lane: 'home',
      status: 'in_progress',
    });
    expect(cellOfDroppable(cellDroppableId(UNFILED_LANE, 'todo'))).toEqual({
      lane: UNFILED_LANE,
      status: 'todo',
    });
    expect(laneOfDroppable(laneDroppableId('home'))).toBe('home');
    expect(laneOfDroppable(cellDroppableId('home', 'todo'))).toBeNull();
    expect(cellOfDroppable(laneDroppableId('home'))).toBeNull();
    expect(cellOfDroppable('h1')).toBeNull();
  });
});

describe('drops that must write nothing', () => {
  it('a card released on itself, on nothing, or by a row the board lost', () => {
    expect(drop('h1', 'h1')).toBeNull();
    expect(drop('h1', null)).toBeNull();
    expect(drop('ghost', 'h1')).toBeNull();
    expect(drop('h1', 'ghost')).toBeNull();
  });

  it('a card released on the empty space of its OWN cell', () => {
    expect(drop('h1', cellDroppableId('home', 'todo'))).toBeNull();
  });

  it('a card released on the header of its OWN lane', () => {
    expect(drop('h1', laneDroppableId('home'))).toBeNull();
    expect(drop('u1', laneDroppableId(UNFILED_LANE))).toBeNull();
  });
});

describe('drops on a card', () => {
  it('inside one cell: reorders, and names no lane', () => {
    expect(drop('h2', 'h1')).toEqual({ status: 'todo', position: 0 });
  });

  it('in another lane of the same column: files the card, at that card’s place in the COLUMN', () => {
    expect(drop('u1', 'w1')).toEqual({ status: 'todo', position: 3, lane: 'work' });
  });

  it('in another lane AND another column: both, in one write', () => {
    expect(drop('u1', 'h3')).toEqual({ status: 'done', position: 0, lane: 'home' });
  });

  it('onto an unfiled card: un-files, explicitly', () => {
    expect(drop('w1', 'u1')).toEqual({ status: 'todo', position: 1, lane: null });
  });
});

describe('drops on the empty space of a cell', () => {
  it('lands after the LAST card of that cell, in column terms', () => {
    // home/todo holds h1 (0) and h2 (2): after h2 is index 2 once u1 has left.
    expect(drop('u1', cellDroppableId('home', 'todo'))).toEqual({
      status: 'todo',
      position: 2,
      lane: 'home',
    });
  });

  it('lands at the end of the column when the cell is empty', () => {
    expect(drop('h1', cellDroppableId('empty', 'todo'))).toEqual({
      status: 'todo',
      position: 3,
      lane: 'empty',
    });
    expect(drop('h1', cellDroppableId('work', 'idea'))).toEqual({
      status: 'idea',
      position: 0,
      lane: 'work',
    });
  });

  it('in another column of the SAME lane: moves the column and names no lane', () => {
    expect(drop('h1', cellDroppableId('home', 'done'))).toEqual({ status: 'done', position: 1 });
  });
});

describe('drops on a lane header', () => {
  it('file the card and leave it where it is in its column', () => {
    expect(drop('h2', laneDroppableId('work'))).toEqual({
      status: 'todo',
      position: 2,
      lane: 'work',
    });
  });

  it('un-file it when the header is the unfiled lane’s', () => {
    expect(drop('h3', laneDroppableId(UNFILED_LANE))).toEqual({
      status: 'done',
      position: 0,
      lane: null,
    });
  });
});

describe('a ticket whose category the board no longer carries', () => {
  const orphan = makeTicket({
    id: 'o1',
    title: 'o1',
    status: 'todo',
    position: 4,
    category_id: 'gone',
  });
  const withOrphan = (status: string) =>
    status === 'todo' ? [...column('todo'), orphan] : column(status);
  const findWithOrphan = (id: string) => (id === 'o1' ? orphan : find(id));

  it('is drawn in the unfiled lane, so dropping it there writes nothing', () => {
    expect(
      resolveLaneDrop(
        'o1',
        cellDroppableId(UNFILED_LANE, 'todo'),
        withOrphan,
        findWithOrphan,
        KNOWN
      )
    ).toBeNull();
  });
});

describe('what a drag announces on a lane board', () => {
  const t = (key: string, values: Record<string, string>) => `${key}:${JSON.stringify(values)}`;

  it('names the lane AND the column at every step', () => {
    const speech = laneSpeech(t);
    expect(speech.movedOver('Buy paint', 'To do', 'Home')).toContain('"lane":"Home"');
    expect(speech.movedOver('Buy paint', 'To do', 'Home')).toContain('"column":"To do"');
    expect(speech.dropped('Buy paint', 'Done', 'Work')).toContain('workboard.dnd.dropped_lane');
    expect(speech.pickedUp('Buy paint', 'To do', 'Home')).toContain('workboard.dnd.picked_up_lane');
  });
});

describe('a drop the reader may not make', () => {
  // The category is the OWNER's: the board mirrors the server's refusal
  // instead of sending a write it knows will come back refused.
  const views = laneViews(
    [
      { category_id: null, name: null, owner_user_id: null, counts_by_status: { todo: 1 } },
      { category_id: 'home', name: 'Home', owner_user_id: 'me', counts_by_status: { todo: 2 } },
      { category_id: 'work', name: 'Work', owner_user_id: 'me', counts_by_status: { todo: 0 } },
      {
        category_id: 'theirs',
        name: 'Theirs',
        owner_user_id: 'peer',
        counts_by_status: { todo: 1 },
      },
    ],
    'me',
    false
  );
  const mine = makeTicket({
    id: 'm1',
    title: 'm1',
    status: 'todo',
    position: 0,
    category_id: 'home',
    owner_user_id: 'me',
  });
  const held = makeTicket({
    id: 'p1',
    title: 'p1',
    status: 'todo',
    position: 1,
    category_id: 'theirs',
    owner_user_id: 'peer',
  });
  const heldToo = makeTicket({
    id: 'p2',
    title: 'p2',
    status: 'todo',
    position: 2,
    category_id: 'theirs',
    owner_user_id: 'peer',
  });
  const rows = [mine, held, heldToo];
  const columnOf = (status: string) => rows.filter(row => row.status === status);
  const findIn = (id: string) => rows.find(row => row.id === id) ?? null;
  const move = (activeId: string, overId: string | null) =>
    laneMove(activeId, overId, columnOf, findIn, views, 'me');

  it('files the reader’s own ticket under another of their lanes, or under nothing', () => {
    expect(move('m1', laneDroppableId('work'))).toEqual({
      status: 'todo',
      position: 0,
      lane: 'work',
    });
    expect(move('m1', cellDroppableId(UNFILED_LANE, 'done'))).toEqual({
      status: 'done',
      position: 0,
      lane: null,
    });
  });

  it('never files it under somebody else’s lane', () => {
    expect(move('m1', laneDroppableId('theirs'))).toBeNull();
    expect(move('m1', 'p1')).toBeNull();
  });

  it('never lets a holder take a ticket out of its owner’s lane', () => {
    expect(move('p1', laneDroppableId('home'))).toBeNull();
    expect(move('p1', laneDroppableId(UNFILED_LANE))).toBeNull();
    expect(move('p1', 'm1')).toBeNull();
  });

  it('still lets a holder move the ticket inside its lane', () => {
    expect(move('p1', cellDroppableId('theirs', 'done'))).toEqual({ status: 'done', position: 0 });
    expect(move('p1', 'p2')).toEqual({ status: 'todo', position: 2 });
  });

  it('writes nothing for a drop that resolves to nothing', () => {
    expect(move('m1', null)).toBeNull();
    expect(move('gone', laneDroppableId('work'))).toBeNull();
  });
});

describe('where a droppable is, for the announcement', () => {
  it('reads a cell, a lane header and a card', () => {
    expect(placeOf(cellDroppableId('work', 'done'), find, KNOWN, 'todo')).toEqual({
      status: 'done',
      lane: 'work',
    });
    // A header files the card and keeps its column: the column is the card's.
    expect(placeOf(laneDroppableId(UNFILED_LANE), find, KNOWN, 'todo')).toEqual({
      status: 'todo',
      lane: null,
    });
    expect(placeOf('h3', find, KNOWN, 'todo')).toEqual({ status: 'done', lane: 'home' });
  });

  it('answers nothing for an id the board does not know', () => {
    expect(placeOf('nobody', find, KNOWN, 'todo')).toBeNull();
  });
});
