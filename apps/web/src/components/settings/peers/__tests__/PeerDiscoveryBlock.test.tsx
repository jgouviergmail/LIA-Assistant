/**
 * PeerDiscoveryBlock — exact-name search + connection request (spec §5.1).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import userEvent from '@testing-library/user-event';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

import { PeerDiscoveryBlock } from '../PeerDiscoveryBlock';

const MATCH = {
  peer_id: 'p1',
  display_name: 'Marie Dupont',
  email_hint: 'm…@g….com',
  relationship: 'none' as const,
};

function setup(over: Record<string, unknown> = {}) {
  const props = {
    lng: 'fr' as const,
    mutating: false,
    search: vi.fn().mockResolvedValue([MATCH]),
    onSendRequest: vi.fn().mockResolvedValue(true),
    ...over,
  };
  renderWithProviders(<PeerDiscoveryBlock {...props} />);
  return props;
}

beforeEach(() => vi.clearAllMocks());

describe('PeerDiscoveryBlock', () => {
  it('searches on form submit with the typed name', async () => {
    const props = setup();
    const input = screen.getByRole('textbox', { name: 'settings.peers.discovery.search_label' });
    await userEvent.type(input, 'Marie Dupont');
    await userEvent.click(
      screen.getByRole('button', { name: 'settings.peers.discovery.search_button' })
    );
    expect(props.search).toHaveBeenCalledWith('Marie Dupont');
    await waitFor(() => expect(screen.getByText('Marie Dupont')).toBeInTheDocument());
    expect(screen.getByText('m…@g….com')).toBeInTheDocument();
  });

  it('does not search on an empty submit', async () => {
    const props = setup();
    await userEvent.click(
      screen.getByRole('button', { name: 'settings.peers.discovery.search_button' })
    );
    expect(props.search).not.toHaveBeenCalled();
  });

  it('shows the no-results state after an unmatched search', async () => {
    const props = setup({ search: vi.fn().mockResolvedValue([]) });
    const input = screen.getByRole('textbox', { name: 'settings.peers.discovery.search_label' });
    await userEvent.type(input, 'Personne Inconnue');
    await userEvent.click(
      screen.getByRole('button', { name: 'settings.peers.discovery.search_button' })
    );
    expect(props.search).toHaveBeenCalled();
    await waitFor(() =>
      expect(screen.getByText('settings.peers.discovery.no_results')).toBeInTheDocument()
    );
  });

  it('sends the request with the optional context message', async () => {
    const props = setup();
    await userEvent.type(
      screen.getByRole('textbox', { name: 'settings.peers.discovery.search_label' }),
      'Marie Dupont'
    );
    await userEvent.click(
      screen.getByRole('button', { name: 'settings.peers.discovery.search_button' })
    );
    await waitFor(() => screen.getByText('Marie Dupont'));
    await userEvent.type(
      screen.getByRole('textbox', { name: 'settings.peers.discovery.context_label' }),
      'Salut, c’est papa'
    );
    await userEvent.click(
      screen.getByRole('button', { name: 'settings.peers.discovery.request_button' })
    );
    expect(props.onSendRequest).toHaveBeenCalledWith('p1', 'Salut, c’est papa');
  });

  it.each([
    ['pending', 'settings.peers.discovery.status_pending'],
    ['connected', 'settings.peers.discovery.status_connected'],
  ] as const)(
    'shows a status badge instead of the request button when already %s',
    async (relationship, badgeKey) => {
      const props = setup({
        search: vi.fn().mockResolvedValue([{ ...MATCH, relationship }]),
      });
      await userEvent.type(
        screen.getByRole('textbox', { name: 'settings.peers.discovery.search_label' }),
        'Marie Dupont'
      );
      await userEvent.click(
        screen.getByRole('button', { name: 'settings.peers.discovery.search_button' })
      );
      await waitFor(() => screen.getByText('Marie Dupont'));
      expect(screen.getByText(badgeKey)).toBeInTheDocument();
      expect(
        screen.queryByRole('button', { name: 'settings.peers.discovery.request_button' })
      ).not.toBeInTheDocument();
      expect(props.onSendRequest).not.toHaveBeenCalled();
    }
  );

  it('disables the request button while mutating', async () => {
    const props = setup({ mutating: true });
    await userEvent.type(
      screen.getByRole('textbox', { name: 'settings.peers.discovery.search_label' }),
      'Marie Dupont'
    );
    await userEvent.click(
      screen.getByRole('button', { name: 'settings.peers.discovery.search_button' })
    );
    await waitFor(() => screen.getByText('Marie Dupont'));
    expect(
      screen.getByRole('button', { name: 'settings.peers.discovery.request_button' })
    ).toBeDisabled();
    expect(props.onSendRequest).not.toHaveBeenCalled();
  });
});
