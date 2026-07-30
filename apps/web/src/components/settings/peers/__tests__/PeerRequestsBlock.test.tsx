/**
 * PeerRequestsBlock — incoming (accept/decline/block) and outgoing pending.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import userEvent from '@testing-library/user-event';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

import { PeerRequestsBlock } from '../PeerRequestsBlock';

const BASE = {
  id: 'conn-1',
  peer_id: 'p1',
  peer_display_name: 'Marie Dupont',
  peer_email_hint: 'm…@g….com',
  status: 'pending' as const,
  requested_at: '2026-07-29T08:00:00Z',
  responded_at: null,
  my_shares: [],
  their_shares: [],
};
const INCOMING = { ...BASE, direction: 'incoming' as const, context_message: 'Salut !' };
const OUTGOING = {
  ...BASE,
  id: 'conn-2',
  direction: 'outgoing' as const,
  context_message: null,
};

function setup(over: Record<string, unknown> = {}) {
  const props = {
    lng: 'fr' as const,
    requests: [INCOMING, OUTGOING],
    mutating: false,
    onRespond: vi.fn().mockResolvedValue(true),
    onBlock: vi.fn().mockResolvedValue(true),
    ...over,
  };
  renderWithProviders(<PeerRequestsBlock {...props} />);
  return props;
}

beforeEach(() => vi.clearAllMocks());

describe('PeerRequestsBlock', () => {
  it('renders the empty state', () => {
    setup({ requests: [] });
    expect(screen.getByText('settings.peers.requests.empty')).toBeInTheDocument();
  });

  it('renders incoming with identity, pinned email hint and the context note', () => {
    setup();
    expect(screen.getAllByText('Marie Dupont').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('m…@g….com').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Salut !/)).toBeInTheDocument();
  });

  it('accept and decline call onRespond with the connection id', async () => {
    const props = setup();
    await userEvent.click(screen.getByRole('button', { name: 'settings.peers.requests.accept' }));
    expect(props.onRespond).toHaveBeenCalledWith('conn-1', true);
    await userEvent.click(screen.getByRole('button', { name: 'settings.peers.requests.decline' }));
    expect(props.onRespond).toHaveBeenCalledWith('conn-1', false);
  });

  it('block from an incoming request targets the peer id', async () => {
    const props = setup();
    await userEvent.click(screen.getByRole('button', { name: 'settings.peers.requests.block' }));
    expect(props.onBlock).toHaveBeenCalledWith('p1');
  });

  it('outgoing shows the waiting badge and no accept button', () => {
    setup({ requests: [OUTGOING] });
    expect(screen.getByText('settings.peers.requests.outgoing_badge')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'settings.peers.requests.accept' })
    ).not.toBeInTheDocument();
  });

  it('disables actions while mutating', () => {
    setup({ mutating: true });
    expect(screen.getByRole('button', { name: 'settings.peers.requests.accept' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'settings.peers.requests.decline' })).toBeDisabled();
  });
});
