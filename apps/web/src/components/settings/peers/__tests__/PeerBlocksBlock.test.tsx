/**
 * PeerBlocksBlock — my blocks with unblock (never who blocked me).
 */

import { describe, it, expect, vi } from 'vitest';
import userEvent from '@testing-library/user-event';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

import { PeerBlocksBlock } from '../PeerBlocksBlock';

const BLOCK = {
  blocked_id: 'user-2',
  blocked_display_name: 'Peer Beta',
  created_at: '2026-07-28T09:00:00Z',
};

describe('PeerBlocksBlock', () => {
  it('renders the empty state without a list', () => {
    renderWithProviders(<PeerBlocksBlock lng="fr" blocks={[]} onUnblock={vi.fn()} mutating={false} />);
    expect(screen.getByText('settings.peers.blocks.empty')).toBeInTheDocument();
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
  });

  it('unblocks via an accessible, keyboard-activable button', async () => {
    const onUnblock = vi.fn().mockResolvedValue(true);
    renderWithProviders(
      <PeerBlocksBlock lng="fr" blocks={[BLOCK]} onUnblock={onUnblock} mutating={false} />
    );
    const button = screen.getByRole('button', { name: /settings\.peers\.blocks\.unblock/ });
    button.focus();
    await userEvent.keyboard('{Enter}');
    expect(onUnblock).toHaveBeenCalledWith('user-2');
  });

  it('disables the unblock button while a mutation is in flight', () => {
    renderWithProviders(
      <PeerBlocksBlock lng="fr" blocks={[BLOCK]} onUnblock={vi.fn()} mutating={true} />
    );
    expect(screen.getByRole('button', { name: /settings\.peers\.blocks\.unblock/ })).toBeDisabled();
  });

  it('falls back to a neutral label when the display name is null', () => {
    renderWithProviders(
      <PeerBlocksBlock
        lng="fr"
        blocks={[{ ...BLOCK, blocked_display_name: null }]}
        onUnblock={vi.fn()}
        mutating={false}
      />
    );
    expect(screen.getByText('settings.peers.blocks.unknown_user')).toBeInTheDocument();
  });
});
