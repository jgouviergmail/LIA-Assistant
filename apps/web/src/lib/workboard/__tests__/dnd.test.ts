/**
 * Where a dropped ticket lands.
 *
 * dnd-kit hands the board « what the pointer was over », which is a card
 * sometimes and a column other times. Every case below is a drop that would
 * otherwise write a move nobody asked for — a card onto itself, onto its own
 * column's empty space, or onto nothing at all — or land it at the wrong index.
 */
import { describe, it, expect } from 'vitest';

import {
  columnDroppableId,
  columnOfDroppable,
  dragSpeech,
  resolveDrop,
  titleOf,
} from '@/lib/workboard/dnd';
import type { TicketRow } from '@/types/workboard';

function ticket(id: string, status: string, position: number): TicketRow {
  return {
    id,
    owner_user_id: 'me',
    parent_id: null,
    title: id,
    description: null,
    status,
    priority: 'medium',
    start_at: null,
    due_at: null,
    assignee_kind: 'human',
    assignee_user_id: null,
    effective_assignee_id: 'me',
    position,
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
  };
}

const BOARD: Record<string, TicketRow[]> = {
  todo: [ticket('a', 'todo', 0), ticket('b', 'todo', 1), ticket('c', 'todo', 2)],
  done: [ticket('z', 'done', 0)],
  idea: [],
};

const column = (status: string) => BOARD[status] ?? [];
const statusOf = (id: string) =>
  Object.values(BOARD)
    .flat()
    .find(row => row.id === id)?.status ?? null;

const drop = (activeId: string, overId: string | null) =>
  resolveDrop(activeId, overId, column, statusOf);

describe('the droppable id of a column', () => {
  it('round-trips, and cannot be mistaken for a ticket id', () => {
    expect(columnOfDroppable(columnDroppableId('todo'))).toBe('todo');
    // A ticket id is a UUID; the prefix is what keeps the two namespaces apart
    // whatever a future id looks like.
    expect(columnOfDroppable('todo')).toBeNull();
    expect(columnOfDroppable('4f0b-todo')).toBeNull();
  });
});

describe('drops that must write nothing', () => {
  it('a card released on itself', () => {
    expect(drop('a', 'a')).toBeNull();
  });

  it('a card released over nothing at all', () => {
    expect(drop('a', null)).toBeNull();
  });

  it('a card released on the empty space of its OWN column', () => {
    // It is already there. Writing the move would renumber the column for a
    // gesture that changed nothing.
    expect(drop('a', columnDroppableId('todo'))).toBeNull();
  });

  it('a card released on its own slot', () => {
    expect(drop('b', 'b')).toBeNull();
  });

  it('a drag whose card the board no longer holds', () => {
    expect(drop('ghost', 'a')).toBeNull();
  });

  it('a drop on a card the board no longer holds', () => {
    expect(drop('a', 'ghost')).toBeNull();
  });
});

describe('drops inside one column', () => {
  it('takes the index of the card it was released on', () => {
    expect(drop('c', 'a')).toEqual({ status: 'todo', position: 0 });
    expect(drop('a', 'c')).toEqual({ status: 'todo', position: 2 });
  });
});

describe('drops into another column', () => {
  it('lands at the index of the card it was released on', () => {
    expect(drop('a', 'z')).toEqual({ status: 'done', position: 0 });
  });

  it('lands at the END when released on a column empty space', () => {
    expect(drop('a', columnDroppableId('done'))).toEqual({ status: 'done', position: 1 });
  });

  it('lands at the start of a column that has nothing in it', () => {
    expect(drop('a', columnDroppableId('idea'))).toEqual({ status: 'idea', position: 0 });
  });
});

describe('what a drag announces', () => {
  const t = (key: string, values: Record<string, string>) =>
    `${key}|${values.title ?? ''}|${values.column ?? ''}`;

  it('names the COLUMN at every step, never an index', () => {
    // « moved to position 3 » tells a screen-reader user nothing about where
    // their ticket went.
    const speech = dragSpeech(t);

    expect(speech.pickedUp('Salle', 'À faire')).toBe('workboard.dnd.picked_up|Salle|À faire');
    expect(speech.movedOver('Salle', 'Terminé')).toBe('workboard.dnd.moved_over|Salle|Terminé');
    expect(speech.dropped('Salle', 'Terminé')).toBe('workboard.dnd.dropped|Salle|Terminé');
    expect(speech.cancelled('Salle')).toBe('workboard.dnd.cancelled|Salle|');
  });

  it('falls back to the id rather than announcing « undefined »', () => {
    const rows = [ticket('a', 'todo', 0)];

    expect(titleOf('a', rows)).toBe('a');
    expect(titleOf('gone', rows)).toBe('gone');
  });
});
