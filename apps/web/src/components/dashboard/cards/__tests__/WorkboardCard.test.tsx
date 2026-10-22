/**
 * WorkboardCard — what is on the person's board, on the dashboard.
 *
 * Five exact counts, each a link into the board narrowed to the very set it
 * counts — « my tickets » first, what the person HOLDS and nothing a LIA or a
 * peer holds (owner request 2026-10-21) — then the first tickets of each set,
 * each a link to the ticket itself. A board with no open ticket is the empty
 * state; a board with open tickets and nothing waiting says so in one line.
 */

import { describe, it, expect, vi } from 'vitest';
import { within } from '@testing-library/react';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { WorkboardCard } from '../WorkboardCard';
import type { CardSection, WorkboardData, WorkboardTicketItem } from '@/types/briefing';

vi.mock('react-i18next', () => {
  const t = (key: string) => key;
  const i18n = { language: 'fr', changeLanguage: vi.fn() };
  return { useTranslation: () => ({ t, i18n }) };
});

const props = { isRefreshing: false, onRefresh: () => {}, staggerIndex: 0 };

function ticket(over: Partial<WorkboardTicketItem> = {}): WorkboardTicketItem {
  return {
    id: 't-1',
    title: 'Book the venue',
    status: 'waiting',
    due_at: null,
    overdue: false,
    ...over,
  };
}

function section(
  data: WorkboardData | null,
  status: CardSection['status'] = 'ok'
): CardSection<WorkboardData> {
  return {
    status,
    data,
    generated_at: '2026-10-03T08:00:00Z',
    error_code: null,
    error_message: null,
    from_cache: false,
    stale_generated_at: null,
    last_attempt_at: null,
  };
}

function data(over: Partial<WorkboardData> = {}): WorkboardData {
  return { needs_me: 0, held_by_lia: 0, overdue: 0, open_total: 0, items: [], ...over };
}

/** The figure link whose visible label is `label`. */
function figure(label: string): HTMLElement {
  const glance = screen.getByRole('list', { name: 'settings.workboard.glance' });
  return within(glance).getByRole('link', { name: new RegExp(label) });
}

const OPEN =
  'status=idea&status=todo&status=in_progress&status=waiting&status=confirming&status=validating';

const MINE = 'settings.workboard.tile_mine';

describe('WorkboardCard', () => {
  it('shows five independent exact counts, each linking to the board narrowed to its set', () => {
    renderWithProviders(
      <WorkboardCard
        {...props}
        section={section(
          data({
            needs_me: 5,
            held_by_me: 4,
            held_by_lia: 2,
            held_by_peers: 7,
            overdue: 3,
            open_total: 12,
          })
        )}
      />
    );

    const glance = screen.getByRole('list', { name: 'settings.workboard.glance' });
    expect(glance.children).toHaveLength(5);
    // « My tickets » leads, and counts what the person holds — never the
    // « needs me » set (5), which also holds late tickets LIA or a peer holds.
    expect(within(glance).getAllByRole('link')[0]).toBe(figure(MINE));
    expect(figure(MINE)).toHaveTextContent('4');
    expect(figure(MINE)).toHaveAttribute('href', `/fr/dashboard/workboard?${OPEN}&assignee=me`);
    expect(figure('settings.workboard.tile_lia')).toHaveTextContent('2');
    expect(figure('settings.workboard.tile_lia')).toHaveAttribute(
      'href',
      `/fr/dashboard/workboard?${OPEN}&assignee=lia`
    );
    expect(figure('dashboard.briefing.cards.workboard.held_by_peers')).toHaveTextContent('7');
    expect(figure('dashboard.briefing.cards.workboard.held_by_peers')).toHaveAttribute(
      'href',
      `/fr/dashboard/workboard?${OPEN}&assignee=peer`
    );
    expect(figure('settings.workboard.tile_overdue')).toHaveTextContent('3');
    expect(figure('settings.workboard.tile_overdue')).toHaveAttribute(
      'href',
      '/fr/dashboard/workboard?overdue=1'
    );
    expect(figure('dashboard.briefing.cards.workboard.tile_open')).toHaveTextContent('12');
    expect(figure('dashboard.briefing.cards.workboard.tile_open')).toHaveAttribute(
      'href',
      `/fr/dashboard/workboard?${OPEN}`
    );
  });

  it('keeps an exact peer zero visible when other open tickets exist', () => {
    renderWithProviders(
      <WorkboardCard
        {...props}
        section={section(data({ held_by_peers: 0, held_by_lia: 2, open_total: 2 }))}
      />
    );

    expect(figure('dashboard.briefing.cards.workboard.held_by_peers')).toHaveTextContent(
      /^0dashboard\.briefing\.cards\.workboard\.held_by_peers$/
    );
  });

  it.each([undefined, null])('does not invent a peer count for legacy cache value %s', value => {
    renderWithProviders(
      <WorkboardCard
        {...props}
        section={section(
          data({ held_by_peers: value, held_by_me: 1, needs_me: 5, held_by_lia: 2, open_total: 12 })
        )}
      />
    );

    const glance = screen.getByRole('list', { name: 'settings.workboard.glance' });
    expect(within(glance).queryByRole('link', { name: /held_by_peers/ })).not.toBeInTheDocument();
    expect(within(glance).getAllByRole('link')).toHaveLength(4);
    expect(figure('dashboard.briefing.cards.workboard.tile_open')).toHaveTextContent('12');
  });

  it.each([undefined, null])(
    'does not invent a « my tickets » count for a cache value %s predating it',
    value => {
      renderWithProviders(
        <WorkboardCard
          {...props}
          section={section(
            data({
              held_by_me: value,
              held_by_peers: 1,
              needs_me: 5,
              held_by_lia: 2,
              open_total: 9,
            })
          )}
        />
      );

      const glance = screen.getByRole('list', { name: 'settings.workboard.glance' });
      expect(within(glance).queryByRole('link', { name: new RegExp(MINE) })).toBeNull();
      expect(within(glance).getAllByRole('link')).toHaveLength(4);
    }
  );

  it('lists my tickets, each linking to the ticket', () => {
    renderWithProviders(
      <WorkboardCard
        {...props}
        section={section({
          ...data({ held_by_me: 2, open_total: 2 }),
          previews: {
            needs_me: [],
            held_by_me: [
              ticket({ id: 'late-1', title: 'Pay the invoice', status: 'todo', overdue: true }),
              ticket({ id: 'ask-2', title: 'Answer LIA', status: 'confirming' }),
            ],
            held_by_lia: [],
            held_by_peers: [],
            overdue: [],
            open_total: [],
          },
        })}
      />
    );

    const mine = screen.getByRole('list', { name: MINE });
    const rows = within(mine).getAllByRole('link');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveAttribute('href', '/fr/dashboard/workboard/late-1');
    expect(rows[0]).toHaveTextContent('Pay the invoice');
    // A late ticket says it is late rather than naming its column.
    expect(rows[0]).toHaveTextContent('workboard.card.overdue');
    expect(rows[1]).toHaveAttribute('href', '/fr/dashboard/workboard/ask-2');
    expect(rows[1]).toHaveTextContent('workboard.columns.confirming');
  });

  it('says in one line that nothing waits when the open board needs nothing', () => {
    renderWithProviders(
      <WorkboardCard {...props} section={section(data({ held_by_lia: 3, open_total: 3 }))} />
    );

    expect(screen.getByText('settings.workboard.nothing_waiting')).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: MINE })).not.toBeInTheDocument();
  });

  it('shows the empty state for a board with no open ticket', () => {
    renderWithProviders(<WorkboardCard {...props} section={section(null, 'empty')} />);

    expect(screen.getByText('dashboard.briefing.cards.workboard.empty')).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('is absent when the instance switched the workboard off', () => {
    renderWithProviders(<WorkboardCard {...props} section={section(null, 'not_configured')} />);

    expect(
      screen.queryByRole('region', { name: 'dashboard.briefing.cards.workboard.title' })
    ).not.toBeInTheDocument();
  });
});

describe('WorkboardCard grouped ticket previews', () => {
  const labels = {
    held_by_me: MINE,
    held_by_lia: 'settings.workboard.tile_lia',
    held_by_peers: 'dashboard.briefing.cards.workboard.held_by_peers',
    overdue: 'settings.workboard.tile_overdue',
    open_total: 'dashboard.briefing.cards.workboard.tile_open',
  };

  it('shows only the first two titles of each corresponding set, including legitimate overlaps', () => {
    const shared = ticket({ id: 'shared', title: 'Shared late peer ticket', overdue: true });
    const mineLate = ticket({ id: 'mine-1', title: 'My late ticket', overdue: true });
    const previews = {
      // Still sent for the hub's sake; the card shows no « needs me » set.
      needs_me: [shared, ticket({ id: 'needs-2', title: 'Needs second' })],
      held_by_me: [mineLate, ticket({ id: 'mine-2', title: 'Mine second' })],
      held_by_lia: [
        ticket({ id: 'lia-1', title: 'LIA first', due_at: '2026-12-31T12:00:00Z' }),
        ticket({ id: 'lia-2', title: 'LIA second' }),
      ],
      held_by_peers: [shared, ticket({ id: 'peer-2', title: 'Peer second' })],
      overdue: [shared, mineLate],
      open_total: [
        shared,
        ticket({ id: 'open-2', title: 'Open second' }),
        ticket({ id: 'open-3', title: 'Must stay bounded' }),
      ],
    };
    const payload = {
      ...data({
        needs_me: 8,
        held_by_me: 5,
        held_by_lia: 3,
        held_by_peers: 6,
        overdue: 4,
        open_total: 12,
      }),
      previews,
      items: [ticket({ id: 'legacy', title: 'Legacy page is not every set' })],
    };
    renderWithProviders(<WorkboardCard {...props} section={section(payload)} />);

    for (const key of Object.keys(labels) as (keyof typeof labels)[]) {
      const links = within(screen.getByRole('list', { name: labels[key] })).getAllByRole('link');
      expect(links).toHaveLength(2);
      expect(links[0]).toHaveTextContent(previews[key][0].title);
      expect(links[1]).toHaveTextContent(previews[key][1].title);
      expect(links[0]).toHaveAttribute('href', `/fr/dashboard/workboard/${previews[key][0].id}`);
    }
    expect(screen.getAllByRole('link', { name: /Shared late peer ticket/ })).toHaveLength(3);
    expect(
      within(screen.getByRole('list', { name: labels.held_by_me })).getAllByRole('link')[0]
    ).toHaveTextContent('workboard.card.overdue');
    expect(
      within(screen.getByRole('list', { name: labels.held_by_lia })).getByText('31/12/2026')
    ).toHaveAttribute('datetime', '2026-12-31T12:00:00Z');
    expect(screen.queryByText('Needs second')).not.toBeInTheDocument();
    expect(screen.queryByText('Must stay bounded')).not.toBeInTheDocument();
    expect(screen.queryByText('Legacy page is not every set')).not.toBeInTheDocument();
    expect(figure(labels.open_total)).toHaveTextContent('12');
  });

  it.each([undefined, null])('lists no ticket when previews=%s is unknown', previews => {
    const payload = {
      ...data({ needs_me: 5, held_by_lia: 2, held_by_peers: 3, open_total: 10 }),
      previews,
      items: [ticket({ id: 'first', title: 'First received need' })],
    };
    renderWithProviders(<WorkboardCard {...props} section={section(payload)} />);

    expect(figure(labels.open_total)).toHaveTextContent('10');
    expect(screen.queryByText('First received need')).not.toBeInTheDocument();
    for (const label of Object.values(labels)) {
      expect(screen.queryByRole('list', { name: label })).not.toBeInTheDocument();
    }
  });

  it('respects known empty previews instead of filling them from the unrelated legacy page', () => {
    const payload = {
      ...data({ needs_me: 1, held_by_peers: 0, open_total: 1 }),
      previews: { needs_me: [], held_by_lia: [], held_by_peers: [], overdue: [], open_total: [] },
      items: [ticket({ title: 'Do not invent membership' })],
    };
    renderWithProviders(<WorkboardCard {...props} section={section(payload)} />);
    expect(screen.queryByText('Do not invent membership')).not.toBeInTheDocument();
    expect(figure(labels.held_by_peers)).toHaveTextContent(/^0/);
  });
});

describe('WorkboardCard « my tickets » migration', () => {
  it('keeps the same focused ticket link when a cache predating « my tickets » is refreshed', () => {
    const retained = ticket({ id: 'retained', title: 'Retained ticket' });
    const initial = {
      ...data({ needs_me: 1, held_by_peers: 0, open_total: 3 }),
      previews: {
        needs_me: [retained],
        held_by_lia: [],
        held_by_peers: [],
        overdue: [],
        open_total: [retained, ticket({ id: 'second' })],
      },
    };
    const { rerender } = renderWithProviders(
      <WorkboardCard {...props} section={section(initial)} />
    );
    const open = 'dashboard.briefing.cards.workboard.tile_open';
    const before = within(screen.getByRole('list', { name: open })).getByRole('link', {
      name: /Retained ticket/,
    });
    before.focus();
    const refreshed = {
      ...initial,
      held_by_me: 1,
      previews: { ...initial.previews, held_by_me: [retained] },
    };
    rerender(<WorkboardCard {...props} section={section(refreshed)} />);

    expect(within(screen.getByRole('list', { name: MINE })).getAllByRole('link')).toHaveLength(1);
    const after = within(screen.getByRole('list', { name: open })).getByRole('link', {
      name: /Retained ticket/,
    });
    expect(after).toBe(before);
    expect(after).toHaveFocus();
    expect(after).toHaveAttribute('href', '/fr/dashboard/workboard/retained');
  });
});
