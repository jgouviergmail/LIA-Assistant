/**
 * PeerConnectionCard — one accepted connection: identity + pinned email hint,
 * MY shares editable, THEIR shares read-only, remove/block behind confirm.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const { confirm } = vi.hoisted(() => ({ confirm: vi.fn() }));
vi.mock('@/components/ui/use-confirm', () => ({
  useConfirm: () => ({ confirm, confirmDialog: null }),
}));

import { PeerConnectionCard } from '../PeerConnectionCard';

const CONNECTION = {
  id: 'conn-1',
  peer_id: 'p1',
  peer_display_name: 'Marie Dupont',
  peer_email_hint: 'm…@g….com',
  peer_email: null,
  status: 'accepted' as const,
  direction: null,
  requested_at: '2026-07-28T08:00:00Z',
  responded_at: '2026-07-28T09:00:00Z',
  context_message: null,
  my_shares: [{ domain: 'calendar' as const, level: 'availability' as const }],
  their_shares: [{ domain: 'task' as const, level: 'titles' as const }],
};

function setup(over: Record<string, unknown> = {}) {
  const props = {
    lng: 'fr' as const,
    connection: CONNECTION,
    mutating: false,
    onSetShare: vi.fn().mockResolvedValue(true),
    onRemove: vi.fn().mockResolvedValue(true),
    onBlock: vi.fn().mockResolvedValue(true),
    ...over,
  };
  const utils = renderWithProviders(<PeerConnectionCard {...props} />);
  return { props, user: utils.user };
}

beforeEach(() => {
  vi.clearAllMocks();
  confirm.mockResolvedValue(true);
});

describe('PeerConnectionCard', () => {
  it('shows identity with the permanently pinned email hint (spec §12.8)', () => {
    setup();
    expect(screen.getByText('Marie Dupont')).toBeInTheDocument();
    expect(screen.getByText('m…@g….com')).toBeInTheDocument();
  });

  // The calendar share moved from a hand-classed native <select> to the
  // design-system Select (layout program, 2026-08-05). Radix Select's open
  // dropdown relies on pointer capture jsdom does not implement, so — same
  // doctrine as `ui/__tests__/select.test.tsx` — the guarded surface is the
  // closed trigger: labelled combobox, current level visible, disabled state.
  it('my calendar share renders as a labelled select showing the current level', () => {
    setup();
    const trigger = screen.getByRole('combobox', {
      name: 'settings.peers.shares.calendar_label',
    });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(trigger).toHaveTextContent('settings.peers.shares.calendar_level.availability');
  });

  it('the task switch shares titles when turned on and removes when off', async () => {
    const { props, user } = setup();
    const taskSwitch = screen.getByRole('switch', { name: 'settings.peers.shares.task_label' });
    await user.click(taskSwitch); // my_shares has no task share → turning ON
    expect(props.onSetShare).toHaveBeenCalledWith('conn-1', 'task', 'titles');
  });

  it('their shares mirror mine as read-only rows, never controls', () => {
    // Same two rows on each side (owner arbitration 2026-08-05): theirs shows
    // VALUES — the task share as shared, the absent calendar share as none.
    setup();
    expect(screen.getByText('settings.peers.shares.their_title')).toBeInTheDocument();
    expect(screen.getByText('settings.peers.shares.task_level.titles')).toBeInTheDocument();
    expect(screen.getByText('settings.peers.shares.calendar_level.none')).toBeInTheDocument();
    // Exactly one combobox (mine) and one switch (mine) — none for theirs.
    expect(screen.getAllByRole('combobox')).toHaveLength(1);
    expect(screen.getAllByRole('switch')).toHaveLength(1);
  });

  it('remove asks for confirmation and calls onRemove when confirmed', async () => {
    const { props, user } = setup();
    await user.click(screen.getByRole('button', { name: 'settings.peers.connections.remove' }));
    expect(confirm).toHaveBeenCalled();
    expect(props.onRemove).toHaveBeenCalledWith('conn-1');
  });

  it('remove does nothing when the confirmation is refused', async () => {
    confirm.mockResolvedValueOnce(false);
    const { props, user } = setup();
    await user.click(screen.getByRole('button', { name: 'settings.peers.connections.remove' }));
    expect(props.onRemove).not.toHaveBeenCalled();
  });

  it('block asks for confirmation and targets the peer id', async () => {
    const { props, user } = setup();
    await user.click(screen.getByRole('button', { name: 'settings.peers.connections.block' }));
    expect(confirm).toHaveBeenCalled();
    expect(props.onBlock).toHaveBeenCalledWith('p1');
  });

  it('disables every action while mutating', () => {
    setup({ mutating: true });
    expect(
      screen.getByRole('combobox', { name: 'settings.peers.shares.calendar_label' })
    ).toBeDisabled();
    expect(screen.getByRole('switch', { name: 'settings.peers.shares.task_label' })).toBeDisabled();
    expect(
      screen.getByRole('button', { name: 'settings.peers.connections.remove' })
    ).toBeDisabled();
  });
});

describe('how a connection is presented', () => {
  it('names the peer with the app’s own avatar, and in bold', () => {
    // A row of connections was told apart by reading, not by looking: every
    // one carried the same generic person glyph. The house avatar hashes a
    // colour from the name, so two connections differ at a glance.
    setup();

    expect(screen.getByText('Marie Dupont')).toHaveClass('font-semibold');

    // Initials, not a photo: this domain publishes no picture for a peer, and
    // adding one would put a personal datum on a surface built to keep the
    // other side unobservable.
    expect(screen.getByText('MD')).toBeInTheDocument();
  });
});
