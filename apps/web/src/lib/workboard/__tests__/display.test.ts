/**
 * What a ticket says about itself — the four claims a card makes.
 *
 * Each test below is a way the board could state something nobody verified:
 * a peer's ticket labelled as mine, a finished ticket reproached for being
 * late, a step counter derived from a page that does not hold every step, and
 * a run refused for quota reported as a failure.
 */
import { describe, it, expect } from 'vitest';

import {
  assigneeParty,
  childProgress,
  isClosed,
  isOverdue,
  ownerParty,
  runState,
  eventLabelKey,
  heldBy,
  assignPatch,
  eventChanges,
} from '@/lib/workboard/display';
import type { TicketRow } from '@/types/workboard';

const ME = 'me-id';
const PEER = 'peer-id';
const PEERS = [{ peer_id: PEER, peer_display_name: 'Marie' }];

function ticket(overrides: Partial<TicketRow> = {}): TicketRow {
  return {
    id: 't',
    owner_user_id: ME,
    parent_id: null,
    title: 'T',
    description: null,
    status: 'todo',
    priority: 'medium',
    start_at: null,
    due_at: null,
    assignee_kind: 'human',
    assignee_user_id: null,
    effective_assignee_id: ME,
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

describe('who holds it', () => {
  it('names LIA before anything else', () => {
    // `assignee_kind = lia` always runs on the OWNER's account, so the id would
    // read as "me" and hide the one fact that matters: nobody human holds it.
    expect(assigneeParty(ticket({ assignee_kind: 'lia' }), ME, PEERS)).toEqual({ kind: 'lia' });
  });

  it('names me, and names a peer', () => {
    expect(assigneeParty(ticket(), ME, PEERS)).toEqual({ kind: 'me' });
    expect(assigneeParty(ticket({ effective_assignee_id: PEER }), ME, PEERS)).toEqual({
      kind: 'peer',
      name: 'Marie',
    });
  });

  it('still says SOMEONE ELSE when the connection is gone', () => {
    // A removed connection leaves the ticket assigned until the peer hook
    // resets it. A blank there would read as « mine ».
    expect(assigneeParty(ticket({ effective_assignee_id: 'stranger' }), ME, PEERS)).toEqual({
      kind: 'unknown',
    });
  });

  it('says nothing about me when the account is not known yet', () => {
    // The session is still loading: claiming a ticket is mine before knowing
    // who I am is a guess.
    expect(assigneeParty(ticket(), undefined, PEERS)).toEqual({ kind: 'unknown' });
  });

  it('names the owner of a ticket a peer handed over', () => {
    expect(ownerParty(ticket({ owner_user_id: PEER }), ME, PEERS)).toEqual({
      kind: 'peer',
      name: 'Marie',
    });
    expect(ownerParty(ticket(), ME, PEERS)).toEqual({ kind: 'me' });
  });
});

describe('is it late', () => {
  const now = new Date('2026-09-09T12:00:00Z');

  it('is late only when a due date has passed', () => {
    expect(isOverdue(ticket({ due_at: '2026-09-08T12:00:00Z' }), now)).toBe(true);
    expect(isOverdue(ticket({ due_at: '2026-09-10T12:00:00Z' }), now)).toBe(false);
    expect(isOverdue(ticket(), now)).toBe(false);
  });

  it('never reproaches a finished ticket', () => {
    // Painting « en retard » on work the person completed is not a fact, it is
    // a reproach.
    for (const status of ['done']) {
      expect(isOverdue(ticket({ due_at: '2026-01-01T00:00:00Z', status }), now)).toBe(false);
    }
    expect(isClosed('done')).toBe(true);
    expect(isClosed('todo')).toBe(false);
  });

  it('says nothing rather than something wrong on an unreadable date', () => {
    expect(isOverdue(ticket({ due_at: 'not-a-date' }), now)).toBe(false);
  });
});

describe('how far along its steps are', () => {
  const parent = ticket({ id: 'p' });
  const children = [
    ticket({ id: 'c1', parent_id: 'p', status: 'done' }),
    ticket({ id: 'c2', parent_id: 'p', status: 'todo' }),
  ];

  it('counts the steps when the page holds the WHOLE board', () => {
    expect(childProgress(parent, [parent, ...children], 3)).toEqual({ done: 1, total: 2 });
  });

  it('says nothing at all when the page is not the whole board', () => {
    // ADR-185: a count shown to somebody is exact or it does not exist. Two
    // steps of five in hand would render « 1/2 » for a ticket with five.
    expect(childProgress(parent, [parent, ...children], 42)).toBeNull();
  });

  it('says nothing for a ticket with no steps', () => {
    expect(childProgress(parent, [parent], 1)).toBeNull();
  });
});

describe('what its last run did', () => {
  it('says nothing about a ticket no run touches', () => {
    expect(runState(ticket({ last_run_outcome: 'failed' }))).toBeNull();
  });

  it('reads the CLAIM before the previous outcome', () => {
    // A ticket LIA is running right now carries a claim; describing it with
    // the outcome of the run before would report a finished state on live work.
    expect(
      runState(
        ticket({
          assignee_kind: 'lia',
          status: 'in_progress',
          last_run_outcome: 'failed',
          run_claimed_at: '2026-09-09T10:00:00Z',
        })
      )
    ).toBe('running');
    expect(
      runState(ticket({ assignee_kind: 'lia', status: 'waiting', last_run_outcome: 'success' }))
    ).toBe('waiting');
  });

  it('reports a failure and a success', () => {
    expect(
      runState(ticket({ assignee_kind: 'lia', status: 'todo', last_run_outcome: 'failed' }))
    ).toBe('failed');
    expect(
      runState(ticket({ assignee_kind: 'lia', status: 'validating', last_run_outcome: 'success' }))
    ).toBe('succeeded');
  });

  it('never reports a skipped run as a failure', () => {
    // Quota refused it, or the conversation was busy: the run did not happen.
    // « Échoué » there would accuse LIA of something it never attempted.
    for (const outcome of ['skipped_quota', 'skipped_busy'] as const) {
      expect(
        runState(ticket({ assignee_kind: 'lia', status: 'todo', last_run_outcome: outcome }))
      ).toBeNull();
    }
  });
});

describe('what the history calls an event', () => {
  const at = '2026-09-09T10:00:00Z';

  it('keeps the kind for anything but a hand-over', () => {
    expect(eventLabelKey({ kind: 'created', payload: null })).toBe('workboard.events.created');
    expect(eventLabelKey({ kind: 'status_changed', payload: { from: 'todo', to: 'done' } })).toBe(
      'workboard.events.status_changed'
    );
  });

  it('calls a hand-over to somebody a hand-over', () => {
    expect(
      eventLabelKey({
        kind: 'assigned',
        payload: { from_kind: 'human', from_user: null, to_kind: 'human', to_user: 'peer' },
      })
    ).toBe('workboard.events.assigned');
  });

  it('calls a hand-over to LIA a hand-over too', () => {
    expect(
      eventLabelKey({
        kind: 'assigned',
        payload: { from_kind: 'human', from_user: null, to_kind: 'lia', to_user: null },
      })
    ).toBe('workboard.events.assigned');
  });

  it('calls a holder handing the ticket back a return', () => {
    expect(
      eventLabelKey({
        kind: 'assigned',
        payload: { from_kind: 'human', from_user: 'peer', to_kind: 'human', to_user: null },
      })
    ).toBe('workboard.events.returned');
  });

  it('names the connection ending when that is why the ticket came back', () => {
    // Written by the release path (lot 5): the actor is nobody, and the
    // reason is the only thing that tells this apart from a deliberate return.
    expect(
      eventLabelKey({
        kind: 'assigned',
        payload: { to_kind: 'human', reason: 'connection_removed' },
      })
    ).toBe('workboard.events.released');
  });

  it('survives an event with no payload at all', () => {
    expect(eventLabelKey({ kind: 'assigned', payload: null })).toBe('workboard.events.assigned');
    void at;
  });
});

describe('who the « holder » control shows, and what changing it sends', () => {
  const base = { owner_user_id: 'owner', assignee_kind: 'human', assignee_user_id: null };

  it('reads a NULL assignee as the owner', () => {
    // `null` IS « the owner holds it » — the convention the whole board rests
    // on, and the shape that lets a departing peer release a ticket.
    expect(heldBy(base)).toBe('me');
  });

  it('reads the owner named explicitly as the owner too', () => {
    expect(heldBy({ ...base, assignee_user_id: 'owner' })).toBe('me');
  });

  it('reads LIA whatever the id column says', () => {
    expect(heldBy({ ...base, assignee_kind: 'lia' })).toBe('lia');
  });

  it('names a peer by their id', () => {
    expect(heldBy({ ...base, assignee_user_id: 'marie' })).toBe('marie');
  });

  it('sends the keywords as keywords and an id as an id', () => {
    // Two different fields: a peer id sent as the keyword is refused, and
    // « me » sent as an id names nobody.
    expect(assignPatch('me')).toEqual({ assignee: 'me' });
    expect(assignPatch('lia')).toEqual({ assignee: 'lia' });
    expect(assignPatch('marie')).toEqual({ assignee_user_id: 'marie' });
  });
});

describe('what a history entry says changed', () => {
  it('gives a column move its two ends', () => {
    // « Colonne modifiée » is a fact nobody can act on.
    expect(eventChanges({ kind: 'status_changed', payload: { from: 'todo', to: 'done' } })).toEqual(
      [{ field: 'status', from: 'todo', to: 'done' }]
    );
  });

  it('gives a priority change its two ends', () => {
    expect(
      eventChanges({ kind: 'priority_changed', payload: { from: 'low', to: 'urgent' } })
    ).toEqual([{ field: 'priority', from: 'low', to: 'urgent' }]);
  });

  it('reports ONLY the date that actually moved', () => {
    // Setting a due date must not claim the start date changed too.
    expect(
      eventChanges({
        kind: 'dates_changed',
        payload: {
          from_start: null,
          to_start: null,
          from_due: null,
          to_due: '2026-10-15T00:00:00Z',
        },
      })
    ).toEqual([{ field: 'due', from: null, to: '2026-10-15T00:00:00Z' }]);
  });

  it('reports both dates when both moved', () => {
    expect(
      eventChanges({
        kind: 'dates_changed',
        payload: {
          from_start: '2026-09-01T00:00:00Z',
          to_start: '2026-09-05T00:00:00Z',
          from_due: '2026-09-30T00:00:00Z',
          to_due: null,
        },
      })
    ).toHaveLength(2);
  });

  it('reads a follow flag as the boolean it is', () => {
    expect(eventChanges({ kind: 'follow_changed', payload: { to: true } })).toEqual([
      { field: 'follow', on: true },
    ]);
  });

  it('says nothing about an entry that carries no payload', () => {
    expect(eventChanges({ kind: 'created', payload: null })).toEqual([]);
    expect(eventChanges({ kind: 'run_started', payload: { run_id: 'r' } })).toEqual([]);
  });
});

describe('what the card says a run did', () => {
  const lia = { status: 'in_progress', assignee_kind: 'lia' as const };

  it('reads « running » from the CLAIM, not from the column', () => {
    // A run in flight still carries the PREVIOUS run's outcome, so reading the
    // outcome first would report a finished state on live work.
    expect(
      runState({ ...lia, last_run_outcome: 'failed', run_claimed_at: '2026-09-09T10:00:00Z' })
    ).toBe('running');
  });

  it('says a run FAILED even though the column still reads « in progress »', () => {
    // A failure leaves the ticket where the run found it. Reading the column
    // said « LIA y travaille » for good, and hid the error line, which only
    // renders on `failed`.
    expect(runState({ ...lia, last_run_outcome: 'failed', run_claimed_at: null })).toBe('failed');
  });

  it('says nothing once the ticket is back in a person hands', () => {
    expect(
      runState({
        status: 'waiting',
        assignee_kind: 'human',
        last_run_outcome: 'waiting',
        run_claimed_at: null,
      })
    ).toBeNull();
  });
});

describe('a ticket LIA gave back', () => {
  it('says LIA handed it back to the reader, never « handed over » nor a bare « returned »', () => {
    // « Rendu » alone meant nothing to the owner (2026-09-09): the label names
    // who gave it and to whom.
    expect(
      eventLabelKey({ kind: 'assigned', payload: { to_kind: 'human', reason: 'handed_back' } })
    ).toBe('workboard.events.returned_by_run');
  });

  it('keeps « returned to the owner » for a peer who hands it back', () => {
    expect(
      eventLabelKey({
        kind: 'assigned',
        payload: { from_kind: 'human', from_user: 'peer', to_kind: 'human', to_user: null },
      })
    ).toBe('workboard.events.returned');
  });
});

describe('what the history calls an answer to a confirmation', () => {
  // Lot 7: the person's word moved the ticket; the wording says which word.
  it('names an approval', () => {
    expect(
      eventLabelKey({
        kind: 'status_changed',
        payload: { from: 'confirming', to: 'todo', reason: 'approve' },
      })
    ).toBe('workboard.events.approved');
  });

  it('names an amendment', () => {
    expect(
      eventLabelKey({
        kind: 'status_changed',
        payload: { from: 'confirming', to: 'todo', reason: 'amend' },
      })
    ).toBe('workboard.events.amended');
  });

  it('names a refusal', () => {
    expect(
      eventLabelKey({
        kind: 'status_changed',
        payload: { from: 'confirming', to: 'done', reason: 'refuse' },
      })
    ).toBe('workboard.events.refused');
  });

  it('keeps the hand-over to LIA that follows an answer a hand-over', () => {
    expect(
      eventLabelKey({
        kind: 'assigned',
        payload: {
          from_kind: 'human',
          from_user: null,
          to_kind: 'lia',
          to_user: null,
          reason: 'approve',
        },
      })
    ).toBe('workboard.events.assigned');
  });

  it('ignores a reason it does not know', () => {
    expect(
      eventLabelKey({ kind: 'status_changed', payload: { from: 'a', to: 'b', reason: 'later' } })
    ).toBe('workboard.events.status_changed');
  });
});
