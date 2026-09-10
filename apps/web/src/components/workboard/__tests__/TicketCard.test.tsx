/**
 * What a card claims about its ticket.
 *
 * Every assertion here is a statement a reader would act on: who holds it,
 * whether it is late, how far its steps have got, what LIA's last run did, and
 * which actions this account is actually allowed to take. The harness echoes
 * translation keys, so a missing key shows up as an absent element rather than
 * as English text nobody would notice.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { TicketCard, type TicketCardProps } from '@/components/workboard/TicketCard';
import type { TicketRow } from '@/types/workboard';

const ME = 'me-id';
const PEER = 'peer-id';

function ticket(overrides: Partial<TicketRow> = {}): TicketRow {
  return {
    id: 't1',
    owner_user_id: ME,
    parent_id: null,
    title: 'Réserver la salle',
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

const handlers = {
  onOpen: vi.fn(),
  onFollowChange: vi.fn(),
  onDelete: vi.fn(),
};

function render(overrides: Partial<TicketCardProps> = {}) {
  const props: TicketCardProps = {
    ticket: ticket(),
    loaded: [ticket()],
    total: 1,
    meId: ME,
    peers: [{ peer_id: PEER, peer_display_name: 'Marie' }],
    lng: 'fr',
    ...handlers,
    ...overrides,
  };
  return renderWithProviders(<TicketCard {...props} />);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('what the card names', () => {
  it('carries the ticket title as its accessible name and as its door', async () => {
    const { user } = render();

    expect(screen.getByRole('article', { name: 'Réserver la salle' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Réserver la salle' }));
    expect(handlers.onOpen).toHaveBeenCalledWith('t1');
  });

  it('says who holds it — me, LIA, or the peer by name', () => {
    render();
    expect(screen.getByText('workboard.party.me')).toBeInTheDocument();

    render({ ticket: ticket({ assignee_kind: 'lia' }) });
    expect(screen.getAllByText('workboard.party.lia').length).toBeGreaterThan(0);

    render({ ticket: ticket({ effective_assignee_id: PEER }) });
    expect(screen.getByText('Marie')).toBeInTheDocument();
  });

  it("names the OWNER when the ticket is not this account's", () => {
    // A ticket a peer handed over: « from Marie » is what tells their work
    // from mine on one board.
    render({ ticket: ticket({ owner_user_id: PEER, effective_assignee_id: ME }) });

    expect(screen.getByText('workboard.party.owned_by')).toBeInTheDocument();
  });
});

describe('the priority is the edge, never a badge', () => {
  it('names every level for a reader who cannot see the colour, and shows none', () => {
    // A badge saying « Élevée » repeated what the leading edge already showed
    // (owner, 2026-09-09). The word stays, visually hidden: the edge is the
    // only place the priority is said in colour, so it cannot be the only
    // place it is said at all.
    for (const priority of ['low', 'medium', 'high', 'urgent']) {
      const { unmount } = render({ ticket: ticket({ priority }) });
      const name = screen.getByText(`workboard.priority.${priority}`);
      expect(name).toHaveClass('sr-only');
      expect(name.closest('[data-testid="ticket-card"]')).not.toBeNull();
      unmount();
    }
  });
});

describe('what the card says first', () => {
  it('puts the holder above the title with the menu at its right, and the bell before the date', () => {
    // A board is scanned for « whose is this » before it is read (owner
    // arbitration, 2026-09-09); the bell then leads the date line UNDER the
    // title (owner, 2026-09-10): whether the chat will speak, and by when.
    const { container } = render({
      ticket: ticket({ follow_owner: true, due_at: '2099-01-01T00:00:00Z' }),
    });
    const follows = (a: Element, b: Element) =>
      Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);

    const menu = container.querySelector('button[aria-haspopup]') as Element;
    const title = screen.getByRole('button', { name: 'Réserver la salle' });
    const bell = screen.getByRole('img', { name: 'workboard.card.followed' });
    const due = screen.getByText('workboard.card.due');

    expect(follows(menu, title)).toBe(true);
    expect(follows(title, bell)).toBe(true);
    expect(follows(bell, due)).toBe(true);
    // The head line holds the holder and the menu, and nothing of the bell.
    const head = title.previousElementSibling as Element;
    expect(head.textContent).toContain('workboard.party.me');
    expect(head.contains(menu)).toBe(true);
    expect(head.contains(bell)).toBe(false);
  });
});

describe('the column and the holder as lists, only where nothing drags', () => {
  const lists = { onStatusChange: vi.fn(), onAssigneeChange: vi.fn() };

  it('carries no list where the card is the drag handle', () => {
    // The card sits IN its column and the column is named right above it:
    // where dragging changes the column, a list repeating it costs a row.
    render({ dragHandle: { role: 'button' }, ...lists });

    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('offers the column and the holder, each named with the ticket, where nothing drags', () => {
    render({ ...lists });

    const column = screen.getByRole('combobox', { name: 'workboard.card.column_of' });
    const holder = screen.getByRole('combobox', { name: 'workboard.card.holder_of' });
    // The closed trigger states the value — its glyph before the name.
    expect(column).toHaveTextContent('workboard.columns.todo');
    expect(column.querySelector('.lucide-circle-dashed')).not.toBeNull();
    expect(holder).toHaveTextContent('workboard.party.me');
    expect(holder.querySelector('.lucide-user')).not.toBeNull();
    // Between the title and the date line.
    const title = screen.getByRole('button', { name: 'Réserver la salle' });
    const bell = screen.getByRole('img', { name: 'workboard.card.not_followed' });
    expect(title.compareDocumentPosition(column) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(column.compareDocumentPosition(bell) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // The holder UNDER the column, never beside it (owner, 2026-09-10): a
    // stacked wrapper, and the holder after the column in reading order.
    expect(column.compareDocumentPosition(holder) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(column.closest('.space-y-2')).not.toBeNull();
    expect(column.closest('.grid')).toBeNull();
  });

  it('writes the same patches the panel writes', async () => {
    const { user } = render({ ...lists });

    await user.click(screen.getByRole('combobox', { name: 'workboard.card.column_of' }));
    await user.click(await screen.findByRole('option', { name: 'workboard.columns.done' }));
    await user.click(screen.getByRole('combobox', { name: 'workboard.card.holder_of' }));
    await user.click(await screen.findByRole('option', { name: 'workboard.party.lia' }));

    expect(lists.onStatusChange).toHaveBeenCalledWith('t1', 'done');
    expect(lists.onAssigneeChange).toHaveBeenCalledWith('t1', { assignee: 'lia' });
  });

  it('wears each column and each holder as a glyph BEFORE its name, in the list', async () => {
    // A native `<option>` holds text only; the list is the application's
    // own so an item can be scanned before it is read (owner, 2026-09-10),
    // and the marks are the registry's — the column header's, the badge's.
    const { user } = render({ ...lists });

    await user.click(screen.getByRole('combobox', { name: 'workboard.card.column_of' }));
    const done = await screen.findByRole('option', { name: 'workboard.columns.done' });
    const glyph = done.querySelector('.lucide-circle-check');
    expect(glyph).not.toBeNull();
    expect(glyph?.parentElement?.firstElementChild).toBe(glyph);
    expect(done).toHaveTextContent(/^workboard\.columns\.done$/);
    await user.keyboard('{Escape}');

    await user.click(screen.getByRole('combobox', { name: 'workboard.card.holder_of' }));
    const lia = await screen.findByRole('option', { name: 'workboard.party.lia' });
    const spark = lia.querySelector('.lucide-sparkles');
    expect(spark?.classList.contains('text-primary')).toBe(true);
    expect(spark?.parentElement?.firstElementChild).toBe(spark);
  });

  it('offers a holder who is not the owner the column only', () => {
    // The service lets a holder hand the ticket BACK and nothing else; the
    // panel offers that as a button, a list with one answer would not.
    render({ meId: PEER, ticket: ticket({ assignee_user_id: PEER }), ...lists });

    expect(screen.getByRole('combobox', { name: 'workboard.card.column_of' })).toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: 'workboard.card.holder_of' })).toBeNull();
  });

  it('draws no list for a surface that cannot act', () => {
    render();

    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });
});

describe('dates', () => {
  it('keeps the date and says « overdue » under it once the due date has passed', () => {
    // The date says by when; the line under it says that it passed (owner,
    // 2026-09-10). Replacing one with the other lost the date.
    render({ ticket: ticket({ due_at: '2020-01-01T00:00:00Z' }) });

    const due = screen.getByText('workboard.card.due');
    const overdue = screen.getByText('workboard.card.overdue');
    expect(due.compareDocumentPosition(overdue) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(overdue.closest('p')).not.toBe(due.closest('div'));
  });

  it('never reproaches a finished ticket', () => {
    render({ ticket: ticket({ due_at: '2020-01-01T00:00:00Z', status: 'done' }) });

    expect(screen.getByText('workboard.card.due')).toBeInTheDocument();
    expect(screen.queryByText('workboard.card.overdue')).not.toBeInTheDocument();
  });
});

describe('steps', () => {
  it('counts them when the page holds the whole board', () => {
    const parent = ticket({ id: 'p' });
    const loaded = [
      parent,
      ticket({ id: 'c1', parent_id: 'p', status: 'done' }),
      ticket({ id: 'c2', parent_id: 'p' }),
    ];
    render({ ticket: parent, loaded, total: 3 });

    expect(screen.getByText('workboard.card.steps')).toBeInTheDocument();
  });

  it('says nothing when the page is only part of the board', () => {
    const parent = ticket({ id: 'p' });
    render({ ticket: parent, loaded: [parent, ticket({ id: 'c1', parent_id: 'p' })], total: 99 });

    expect(screen.queryByText('workboard.card.steps')).not.toBeInTheDocument();
  });
});

describe("what LIA's last run did", () => {
  it('reports a failure as a SENTENCE, keeping the evidence in the tooltip', () => {
    // `last_run_error` stores `code: technical message`. Printing it whole put
    // `workboard_run_failed` — a machine identifier, in English — on the card
    // in all six languages, while the backend's own contract says the board
    // resolves the code from the locales.
    render({
      ticket: ticket({
        assignee_kind: 'lia',
        last_run_outcome: 'failed',
        last_run_error: 'workboard_run_failed: provider timeout',
      }),
    });

    expect(screen.getByText('workboard.card.run_failed')).toBeInTheDocument();
    const line = screen.getByText('workboard.run_errors.run_failed');
    expect(line).toBeInTheDocument();
    expect(line).toHaveAttribute('title', 'provider timeout');
    expect(screen.queryByText(/workboard_run_failed:/)).not.toBeInTheDocument();
  });

  it('translates a bare code, which carries no technical message at all', () => {
    render({
      ticket: ticket({
        assignee_kind: 'lia',
        last_run_outcome: 'failed',
        last_run_error: 'workboard_assignee_inactive',
      }),
    });

    expect(screen.getByText('workboard.run_errors.assignee_inactive')).toBeInTheDocument();
    expect(screen.queryByText('workboard_assignee_inactive')).not.toBeInTheDocument();
  });

  it('never reports a skipped run as a failure', () => {
    render({ ticket: ticket({ assignee_kind: 'lia', last_run_outcome: 'skipped_quota' }) });

    expect(screen.queryByText('workboard.card.run_failed')).not.toBeInTheDocument();
    expect(screen.queryByText(/skipped/)).not.toBeInTheDocument();
  });
});

describe('what this account may do', () => {
  it('offers deletion to the owner', async () => {
    const { user } = render();
    await user.click(screen.getByRole('button', { name: 'workboard.card.delete' }));

    expect(handlers.onDelete).toHaveBeenCalledWith(expect.objectContaining({ id: 't1' }));
  });

  it('never offers deletion to a holder who is not the owner', () => {
    // The service refuses it (`workboard_peer_cannot_delete`); a button that
    // can only ever fail is a question with one answer.
    render({ ticket: ticket({ owner_user_id: PEER, effective_assignee_id: ME }) });

    expect(screen.queryByRole('button', { name: 'workboard.card.delete' })).not.toBeInTheDocument();
  });

  it('toggles the flag of the side this account is on', async () => {
    // The owner's bell is not the holder's: each side follows its own.
    const { user } = render({ ticket: ticket({ follow_owner: true }) });
    await user.click(screen.getByRole('button', { name: 'workboard.card.follow_off' }));
    expect(handlers.onFollowChange).toHaveBeenCalledWith('t1', false);

    vi.clearAllMocks();
    const holder = render({
      ticket: ticket({ owner_user_id: PEER, effective_assignee_id: ME, follow_assignee: false }),
    });
    await holder.user.click(screen.getAllByRole('button', { name: 'workboard.card.follow_on' })[0]);
    expect(handlers.onFollowChange).toHaveBeenCalledWith('t1', true);
  });
});

describe('the whole card is the handle, and the title is still the door', () => {
  it('spreads the drag listeners on the card, not on a 16 px grip', async () => {
    // A dedicated grip is not a touch target. The listeners belong to the card
    // — what a finger actually reaches for — and the grip stays as the icon
    // that says the card can be picked up.
    const onPointerDown = vi.fn();
    const { user } = render({ dragHandle: { role: 'button', onPointerDown } });

    const card = screen.getByTestId('ticket-card');
    expect(card).toHaveAttribute('aria-label', 'workboard.card.drag_card');
    await user.pointer({ target: card, keys: '[MouseLeft>]' });
    expect(onPointerDown).toHaveBeenCalled();
  });

  it('keeps the title opening the ticket rather than starting a drag', async () => {
    // The title stops the pointer and the keys before they reach the card's
    // listeners: opening a ticket can never be read as the start of a drag.
    const onPointerDown = vi.fn();
    const { user } = render({ dragHandle: { role: 'button', onPointerDown } });

    const title = screen.getByText('Réserver la salle');
    await user.click(title);

    expect(handlers.onOpen).toHaveBeenCalledWith('t1');
    expect(onPointerDown).not.toHaveBeenCalled();
  });

  it('shows no grip at all where the board cannot be dragged', () => {
    const { container } = render();

    expect(container.querySelector('.lucide-grip-vertical')).toBeNull();
  });

  it('stretches the door over the whole card where nothing can be dragged', () => {
    // Below `lg` a finger that lands on the date or the bell opens the
    // ticket: the title button covers the card through a pseudo-element,
    // and the menu is raised above it (owner, 2026-09-10).
    render();

    expect(screen.getByRole('button', { name: 'Réserver la salle' }).className).toContain(
      'after:absolute'
    );
    expect(
      screen.getByRole('button', { name: 'workboard.card.actions' }).closest('.z-10')
    ).not.toBeNull();
  });

  it('keeps the door to the title where the card is the drag handle', () => {
    render({ dragHandle: { role: 'button' } });

    expect(screen.getByRole('button', { name: 'Réserver la salle' }).className).not.toContain(
      'after:absolute'
    );
  });
});

describe('every person wears the theme colour', () => {
  it('colours the holder badge for me, for LIA and for a peer alike', () => {
    // LIA's spark alone carried the accent; « Moi » and a connection stayed
    // grey (owner, 2026-09-10). One map colours the three.
    const mine = render();
    expect(screen.getByTestId('ticket-card').querySelector('.lucide-user')?.classList).toContain(
      'text-primary'
    );
    mine.unmount();

    render({ ticket: ticket({ assignee_user_id: PEER, effective_assignee_id: PEER }) });
    expect(screen.getByTestId('ticket-card').querySelector('.lucide-users')?.classList).toContain(
      'text-primary'
    );
  });
});

describe('priority and lateness are visible before they are read', () => {
  it('ranks the priority on the leading edge', () => {
    // A ramp, not a binary: `high` and `urgent` share a badge tone because
    // both are simply « loud », and an edge painting them alike would carry
    // nothing.
    const edges = new Map<string, string>();
    for (const priority of ['low', 'medium', 'high', 'urgent']) {
      const { unmount } = render({ ticket: ticket({ priority }) });
      edges.set(priority, screen.getByTestId('ticket-card').className);
      unmount();
    }

    expect(edges.get('urgent')).toContain('border-l-destructive');
    expect(edges.get('high')).toContain('border-l-warning');
    expect(new Set(edges.values()).size).toBe(4);
  });

  it('marks a late ticket beyond its colour', () => {
    // Colour is never the only carrier: an outline, an icon AND the sentence.
    render({ ticket: ticket({ due_at: '2020-01-01T00:00:00Z' }) });

    const card = screen.getByTestId('ticket-card');
    // An INNER frame — a pseudo-element on the padding box, so the priority
    // edge stays outside it — never an outline around the whole card.
    expect(card.className).toContain('before:absolute before:inset-0');
    expect(card.className).toContain('before:border-destructive');
    expect(card.className).toContain('before:pointer-events-none');
    expect(card.className).not.toContain('outline');
    // The frame BREATHES where motion is welcome (owner, 2026-09-10), and
    // only there: the utility is gated on `motion-safe`, so a reader who
    // asked for less motion keeps a still frame, red.
    expect(card.className).toContain('motion-safe:before:animate-overdue-pulse');
    expect(card.className).not.toMatch(/(^|\s)animate-overdue-pulse/);
    const icon = card.querySelector('.lucide-triangle-alert');
    expect(icon).not.toBeNull();
    // Boxed like the bell above it — the same 20 px column — so « en retard »
    // starts exactly under the date (owner, 2026-09-10).
    const bell = screen.getByRole('img', { name: 'workboard.card.not_followed' });
    expect(icon?.parentElement?.className).toContain('h-5 w-5');
    expect(bell.className).toContain('h-5 w-5');
    expect(screen.getByText('workboard.card.overdue')).toBeInTheDocument();
  });

  it('marks nothing on a ticket that is not late', () => {
    render({ ticket: ticket({ due_at: '2999-01-01T00:00:00Z' }) });

    const card = screen.getByTestId('ticket-card');
    expect(card.className).not.toContain('before:border-destructive');
    expect(card.className).not.toContain('animate-overdue-pulse');
    expect(card.querySelector('.lucide-triangle-alert')).toBeNull();
  });
});

describe('a draggable card and its title never answer to one name', () => {
  it('names the card for the move and the button for the door', () => {
    render({ dragHandle: { role: 'button' } });

    // Two controls, two names: « move this ticket » and the title itself.
    expect(screen.getByTestId('ticket-card')).toHaveAttribute(
      'aria-label',
      'workboard.card.drag_card'
    );
    expect(screen.getByRole('button', { name: 'Réserver la salle' })).toBeInTheDocument();
  });

  it('keeps the plain title as the name where nothing can be dragged', () => {
    render();

    expect(screen.getByRole('article', { name: 'Réserver la salle' })).toBeInTheDocument();
  });
});

describe('the three holders are told apart before they are read', () => {
  const glyphs = (overrides: Parameters<typeof ticket>[0]) => {
    const { unmount } = render({ ticket: ticket(overrides) });
    const marks = [...screen.getByTestId('ticket-card').querySelectorAll('svg')]
      .map(node => node.getAttribute('class') ?? '')
      .join(' ');
    unmount();
    return marks;
  };

  it('gives me, LIA and a peer three different glyphs', () => {
    expect(glyphs({ assignee_kind: 'human', assignee_user_id: null })).toContain('lucide-user');
    expect(glyphs({ assignee_kind: 'lia', assignee_user_id: null })).toContain('lucide-sparkles');
    expect(
      glyphs({ assignee_kind: 'human', assignee_user_id: PEER, effective_assignee_id: PEER })
    ).toContain('lucide-users');
  });

  it('keeps the word beside the glyph', () => {
    // The icon carries the KIND, the word says WHO — a reader who cannot see
    // the glyph loses nothing.
    render({ ticket: ticket({ assignee_kind: 'lia', assignee_user_id: null }) });

    expect(screen.getByText('workboard.party.lia')).toBeInTheDocument();
  });
});

describe('the card never badges what its column already says', () => {
  it('shows no run badge on a ticket LIA is working on', () => {
    // « LIA y travaille » repeats the « En cours » header the card sits under.
    render({
      ticket: ticket({ status: 'in_progress', assignee_kind: 'lia', assignee_user_id: null }),
    });

    expect(screen.queryByText('workboard.card.run_running')).not.toBeInTheDocument();
  });

  it('shows no run badge on a ticket waiting for the person', () => {
    // « Attend votre retour » did not even fit the column it repeated.
    render({
      ticket: ticket({ status: 'waiting', assignee_kind: 'lia', assignee_user_id: null }),
    });

    expect(screen.queryByText('workboard.card.run_waiting')).not.toBeInTheDocument();
  });

  it('still says when a run FAILED, which no column says', () => {
    render({
      ticket: ticket({
        status: 'in_progress',
        assignee_kind: 'lia',
        assignee_user_id: null,
        last_run_outcome: 'failed',
        last_run_error: 'workboard_run_reaped',
      }),
    });

    expect(screen.getByText('workboard.card.run_failed')).toBeInTheDocument();
    expect(screen.getByText('workboard.run_errors.run_reaped')).toBeInTheDocument();
  });
});

describe('the card says whether this account follows the ticket', () => {
  it('shows the bell when I follow it', () => {
    render({ ticket: ticket({ follow_owner: true }) });

    expect(screen.getByRole('img', { name: 'workboard.card.followed' })).toBeInTheDocument();
  });

  it('shows the muted bell when I do not', () => {
    render({ ticket: ticket({ follow_owner: false }) });

    expect(screen.getByRole('img', { name: 'workboard.card.not_followed' })).toBeInTheDocument();
  });

  it('reads the HOLDER flag for a peer who holds it', () => {
    // Each side follows its own flag: the owner bell is not the holder bell.
    render({
      meId: PEER,
      ticket: ticket({ assignee_user_id: PEER, follow_owner: true, follow_assignee: false }),
    });

    expect(screen.getByRole('img', { name: 'workboard.card.not_followed' })).toBeInTheDocument();
  });
});

describe('what tells urgent from high at a glance', () => {
  it('gives an urgent ticket its own ground', () => {
    // The two share a badge tone — measured, a red-100 ground and a warning/10
    // ground read as one level — so four pixels of edge were all that told
    // them apart on a board read across.
    const { container } = render({ ticket: ticket({ priority: 'urgent' }) });

    expect(container.querySelector('[data-testid="ticket-card"]')?.className).toContain('bg-rose');
  });

  it("leaves every other priority on the card's normal surface", () => {
    for (const priority of ['high', 'medium', 'low']) {
      const { container, unmount } = render({ ticket: ticket({ priority }) });
      expect(container.querySelector('[data-testid="ticket-card"]')?.className).not.toContain(
        'bg-rose'
      );
      unmount();
    }
  });

  it('shows no grip: the whole card is the handle', () => {
    const { container } = render({ dragHandle: {} });

    // A glyph pointing at a handle that does not exist costs width and lies.
    expect(container.querySelector('.lucide-grip-vertical')).toBeNull();
  });
});
