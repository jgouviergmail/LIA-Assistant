/**
 * PeerAccessLogBlock — the transparency view: who read my shared data.
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

import { PeerAccessLogBlock } from '../PeerAccessLogBlock';

const ENTRY = {
  accessor_display_name: 'Marie Dupont',
  domain: 'calendar',
  tool_name: 'get_peer_availability',
  created_at: '2026-07-29T10:00:00Z',
};

describe('PeerAccessLogBlock', () => {
  it('renders the empty state when nobody read anything', () => {
    renderWithProviders(<PeerAccessLogBlock lng="fr" entries={[]} />);
    expect(screen.getByText('settings.peers.access_log.empty')).toBeInTheDocument();
  });

  it('lists each read with accessor, localized domain label and a time element', () => {
    renderWithProviders(<PeerAccessLogBlock lng="fr" entries={[ENTRY]} />);
    expect(screen.getByText(/Marie Dupont/)).toBeInTheDocument();
    expect(screen.getByText(/settings\.peers\.domains\.calendar/)).toBeInTheDocument();
    // Semantic <time> with the machine-readable instant (a11y + tooling).
    const time = document.querySelector('time');
    expect(time).not.toBeNull();
    expect(time).toHaveAttribute('dateTime', ENTRY.created_at);
  });

  it('is a semantic list', () => {
    renderWithProviders(<PeerAccessLogBlock lng="fr" entries={[ENTRY]} />);
    expect(screen.getByRole('list')).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
  });
});
