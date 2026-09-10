/**
 * What the history block tells a reader about a ticket's past.
 *
 * Found by a cold review of lots 4 and 5 together: the release path writes an
 * « assigned » event when a connection ends, the block rendered every
 * « assigned » as « Handed over », and a person whose peer had just left read
 * the opposite of what happened on a ticket that had come back to them. The
 * harness echoes translation keys, so the assertions read the key each event
 * resolves to.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import {
  CommentsBlock,
  HistoryBlock,
  LastRunBlock,
} from '@/components/workboard/TicketDetailSections';
import type { CommentRow, EventRow, TicketRow } from '@/types/workboard';

// The figures follow the header's own « show figures » switch, exactly as
// the chat's per-message line does.
const account = vi.hoisted(() => ({ value: { id: 'me', tokens_display_enabled: true } }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: account.value }) }));

beforeEach(() => {
  account.value = { id: 'me', tokens_display_enabled: true };
});

function event(overrides: Partial<EventRow> = {}): EventRow {
  return {
    id: 'e1',
    actor_kind: 'user',
    actor_user_id: 'me',
    kind: 'created',
    payload: null,
    created_at: '2026-09-09T10:00:00Z',
    ...overrides,
  };
}

describe('HistoryBlock', () => {
  it('says so when there is nothing to tell', () => {
    renderWithProviders(<HistoryBlock events={[]} locale="fr" />);

    expect(screen.getByText('workboard.detail.no_history')).toBeInTheDocument();
  });

  it('names each event by its kind', () => {
    renderWithProviders(
      <HistoryBlock events={[event(), event({ id: 'e2', kind: 'status_changed' })]} locale="fr" />
    );

    expect(screen.getByText(/workboard\.events\.created/)).toBeInTheDocument();
    expect(screen.getByText(/workboard\.events\.status_changed/)).toBeInTheDocument();
  });

  it('does NOT call a ticket that came back « handed over »', () => {
    renderWithProviders(
      <HistoryBlock
        events={[
          event({
            kind: 'assigned',
            actor_kind: 'user',
            actor_user_id: null,
            payload: { to_kind: 'human', reason: 'connection_removed' },
          }),
        ]}
        locale="fr"
      />
    );

    expect(screen.getByText(/workboard\.events\.released/)).toBeInTheDocument();
    expect(screen.queryByText(/workboard\.events\.assigned/)).not.toBeInTheDocument();
  });

  it('tells a deliberate return from a hand-over', () => {
    renderWithProviders(
      <HistoryBlock
        events={[
          event({
            id: 'e1',
            kind: 'assigned',
            payload: { from_kind: 'human', from_user: null, to_kind: 'human', to_user: 'peer' },
          }),
          event({
            id: 'e2',
            kind: 'assigned',
            payload: { from_kind: 'human', from_user: 'peer', to_kind: 'human', to_user: null },
          }),
        ]}
        locale="fr"
      />
    );

    expect(screen.getByText(/workboard\.events\.assigned/)).toBeInTheDocument();
    expect(screen.getByText(/workboard\.events\.returned/)).toBeInTheDocument();
  });

  it('lets each label carry its own punctuation', () => {
    // A literal « : » published French punctuation in six languages; the
    // separator is a translated key, beside the labels it joins.
    renderWithProviders(
      <HistoryBlock
        events={[event({ kind: 'priority_changed', payload: { from: 'medium', to: 'urgent' } })]}
        locale="fr"
      />
    );

    expect(
      screen.getByText(/workboard\.history\.priorityworkboard\.history\.separator/)
    ).toBeInTheDocument();
    expect(screen.queryByText(/ : /)).not.toBeInTheDocument();
  });

  it('formats the instant in the reader locale', () => {
    renderWithProviders(<HistoryBlock events={[event()]} locale="fr" />);

    // A French short date carries the day before the month.
    expect(screen.getByText(/09\/09\/2026/)).toBeInTheDocument();
  });
});

describe('CommentsBlock', () => {
  function comment(overrides: Partial<CommentRow> = {}): CommentRow {
    return {
      id: 'c1',
      author_kind: 'lia',
      author_user_id: null,
      body: 'Deux créneaux possibles.',
      run_id: null,
      created_at: '2026-09-09T14:30:00Z',
      ...overrides,
    };
  }

  it('dates every entry, so a thread can be read in order', () => {
    // A run's question and the reply it drew are one conversation only if the
    // reader can see which came first.
    renderWithProviders(
      <CommentsBlock comments={[comment()]} locale="fr">
        <div />
      </CommentsBlock>
    );

    const stamp = screen.getByText(/09\/09\/2026/);
    expect(stamp.tagName).toBe('TIME');
    expect(stamp).toHaveAttribute('dateTime', '2026-09-09T14:30:00Z');
  });

  it('still says who spoke', () => {
    renderWithProviders(
      <CommentsBlock comments={[comment({ author_kind: 'user' })]} locale="fr">
        <div />
      </CommentsBlock>
    );

    expect(screen.getByText('workboard.detail.author_user')).toBeInTheDocument();
  });

  it('says so when nothing has been said', () => {
    renderWithProviders(
      <CommentsBlock comments={[]} locale="fr">
        <div />
      </CommentsBlock>
    );

    expect(screen.getByText('workboard.detail.no_comment')).toBeInTheDocument();
  });
});

describe('LastRunBlock', () => {
  function ticket(overrides: Partial<TicketRow> = {}): TicketRow {
    return {
      id: 't1',
      owner_user_id: 'me',
      parent_id: null,
      title: 'Réserver la salle',
      description: null,
      status: 'validating',
      priority: 'medium',
      start_at: null,
      due_at: null,
      assignee_kind: 'lia',
      assignee_user_id: null,
      effective_assignee_id: 'me',
      position: 0,
      follow_owner: false,
      follow_assignee: false,
      created_by: 'user',
      status_changed_at: '2026-09-09T10:00:00Z',
      run_count: 1,
      run_claimed_at: null,
      last_run_at: '2026-09-09T08:30:00Z',
      last_run_outcome: 'success',
      last_run_error: null,
      last_run_tokens_in: 1840,
      last_run_tokens_out: 260,
      last_run_cost_eur: 0.012,
      created_at: '2026-09-09T10:00:00Z',
      execution_mode: 'react',
      total_tokens_in: 1840,
      total_tokens_out: 260,
      total_tokens_cache: 0,
      total_google_requests: 0,
      total_cost_eur: 0.012,
      updated_at: '2026-09-09T10:00:00Z',
      ...overrides,
    };
  }

  it("says the run's verdict in its own words, never the column", () => {
    // A failed run leaves the ticket in the column it was found in, so the
    // column under « last run » said nothing about the run (cold review).
    renderWithProviders(<LastRunBlock ticket={ticket()} locale="fr" />);

    expect(screen.getByText('workboard.detail.outcome_success')).toBeInTheDocument();
    expect(screen.queryByText('workboard.columns.validating')).not.toBeInTheDocument();
  });

  it("shows the run's own figures in the meter's vocabulary, to the cent of a cent", () => {
    renderWithProviders(<LastRunBlock ticket={ticket()} locale="fr" />);

    expect(screen.getByText(/1 840 IN|1,840 IN/)).toBeInTheDocument();
    expect(screen.getByText(/260 OUT/)).toBeInTheDocument();
    // Six decimals, as a message's own line shows its cost.
    expect(screen.getByText(/0,012000|0\.012000/)).toBeInTheDocument();
  });

  it('keeps the figures for itself while the reader has them switched off', () => {
    account.value = { id: 'me', tokens_display_enabled: false };
    renderWithProviders(<LastRunBlock ticket={ticket()} locale="fr" />);

    expect(screen.getByText('workboard.detail.outcome_success')).toBeInTheDocument();
    expect(screen.queryByText(/IN$/)).not.toBeInTheDocument();
  });

  it('says why a postponed run did nothing, and shows no figure', () => {
    // A quota refusal is not a failure (ADR-272): it is named, not blamed.
    renderWithProviders(
      <LastRunBlock
        ticket={ticket({ last_run_outcome: 'skipped_quota', last_run_cost_eur: null })}
        locale="fr"
      />
    );

    expect(screen.getByText('workboard.detail.outcome_skipped_quota')).toBeInTheDocument();
    expect(screen.queryByText(/IN$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/€/)).not.toBeInTheDocument();
  });

  it('says WHY a run failed in the reader’s language, with the evidence under it', () => {
    // The stored shape is `code: technical message`, and the panel used to
    // print it whole — so `workboard_run_failed` was the sentence a person
    // read, in English, in all six languages.
    renderWithProviders(
      <LastRunBlock
        ticket={ticket({
          last_run_outcome: 'failed',
          last_run_error: 'workboard_run_failed: Agenda injoignable',
        })}
        locale="fr"
      />
    );

    expect(screen.getByText('workboard.detail.outcome_failed')).toBeInTheDocument();
    expect(screen.getByText('workboard.run_errors.run_failed')).toBeInTheDocument();
    // The evidence stays, under the sentence and muted — never as the heading.
    expect(screen.getByText('Agenda injoignable')).toBeInTheDocument();
    expect(screen.queryByText(/workboard_run_failed:/)).not.toBeInTheDocument();
  });

  it('shows a bare code as its sentence and nothing else', () => {
    renderWithProviders(
      <LastRunBlock
        ticket={ticket({ last_run_outcome: 'failed', last_run_error: 'workboard_run_reaped' })}
        locale="fr"
      />
    );

    expect(screen.getByText('workboard.run_errors.run_reaped')).toBeInTheDocument();
    expect(screen.queryByText('workboard_run_reaped')).not.toBeInTheDocument();
  });

  it('renders nothing before any run', () => {
    const { container } = renderWithProviders(
      <LastRunBlock ticket={ticket({ last_run_outcome: null })} locale="fr" />
    );

    expect(container).toBeEmptyDOMElement();
  });
});
