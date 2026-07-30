/**
 * PeerMessageActions — quick actions under peer chat bubbles (peers Lot 7).
 *
 * The load-bearing behaviors: the block renders NOTHING on non-peer bubbles
 * (it is grafted under every assistant message); Reply only prefills the
 * composer (A4 — a prefill never sends anything); Block goes through the
 * house confirm before POSTing; Accept/Decline answer the request in one
 * click and freeze into the verdict; backend `peers_*` codes surface through
 * the shared localized toast mapping, never raw.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { ApiError } from '@/lib/api-client';

const { mutate } = vi.hoisted(() => ({ mutate: vi.fn(async (): Promise<unknown> => ({})) }));
vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({ mutate, loading: false }),
}));

const { confirm } = vi.hoisted(() => ({ confirm: vi.fn() }));
vi.mock('@/components/ui/use-confirm', () => ({
  useConfirm: () => ({ confirm, confirmDialog: null }),
}));

const { toast } = vi.hoisted(() => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));
vi.mock('sonner', () => ({ toast }));

import { PeerMessageActions } from '../PeerMessageActions';

const MESSAGE_META = {
  type: 'proactive_peer_message',
  target_id: 'msg-1',
  sender_id: 'peer-1',
  sender_name: 'Marie Dupont',
};

const REQUEST_META = {
  type: 'proactive_peer_request',
  target_id: 'conn-1',
  peer_event: 'request_created',
  peer_id: 'peer-1',
  peer_name: 'Marie Dupont',
};

beforeEach(() => {
  vi.clearAllMocks();
  confirm.mockResolvedValue(true);
});

describe('PeerMessageActions — scoping', () => {
  it('renders nothing without peer metadata', () => {
    const { container } = renderWithProviders(
      <PeerMessageActions metadata={{ type: 'proactive_interest' }} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing on a request-outcome notice (accepted/removed kinds)', () => {
    const { container } = renderWithProviders(
      <PeerMessageActions
        metadata={{ ...REQUEST_META, peer_event: 'request_accepted' }}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe('PeerMessageActions — relayed message', () => {
  it('Reply prefills the composer and sends nothing', async () => {
    const onPrefillComposer = vi.fn();
    const { user } = renderWithProviders(
      <PeerMessageActions metadata={MESSAGE_META} onPrefillComposer={onPrefillComposer} />
    );
    await user.click(screen.getByRole('button', { name: /chat.peer.reply/ }));
    expect(onPrefillComposer).toHaveBeenCalledWith('chat.peer.reply_prefill');
    expect(mutate).not.toHaveBeenCalled();
  });

  it('Block asks the house confirm, POSTs, then hides itself', async () => {
    const { user } = renderWithProviders(<PeerMessageActions metadata={MESSAGE_META} />);
    await user.click(screen.getByRole('button', { name: /chat.peer.block/ }));
    expect(confirm).toHaveBeenCalled();
    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith('/peers/blocks', { peer_id: 'peer-1' })
    );
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('settings.peers.blocks.blocked'));
    expect(screen.queryByRole('button', { name: /chat.peer.block/ })).not.toBeInTheDocument();
  });

  it('Block does nothing when the confirmation is refused', async () => {
    confirm.mockResolvedValue(false);
    const { user } = renderWithProviders(<PeerMessageActions metadata={MESSAGE_META} />);
    await user.click(screen.getByRole('button', { name: /chat.peer.block/ }));
    expect(mutate).not.toHaveBeenCalled();
  });

  it('maps a backend peers_* code through the localized toast, never raw', async () => {
    mutate.mockRejectedValueOnce(new ApiError('conflict', 409, { detail: 'peers_conflict' }));
    const { user } = renderWithProviders(<PeerMessageActions metadata={MESSAGE_META} />);
    await user.click(screen.getByRole('button', { name: /chat.peer.block/ }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('settings.peers.errors.conflict')
    );
  });
});

describe('PeerMessageActions — incoming connection request', () => {
  it('Accept responds and freezes into the accepted verdict', async () => {
    const { user } = renderWithProviders(<PeerMessageActions metadata={REQUEST_META} />);
    await user.click(screen.getByRole('button', { name: /settings.peers.requests.accept/ }));
    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith('/peers/requests/conn-1/respond', { accept: true })
    );
    await waitFor(() =>
      expect(screen.getByText('settings.peers.requests.accepted')).toBeInTheDocument()
    );
    expect(screen.queryByRole('button', { name: /settings.peers.requests.accept/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /settings.peers.requests.decline/ })).toBeNull();
  });

  it('Decline responds and freezes into the declined verdict', async () => {
    const { user } = renderWithProviders(<PeerMessageActions metadata={REQUEST_META} />);
    await user.click(screen.getByRole('button', { name: /settings.peers.requests.decline/ }));
    await waitFor(() =>
      expect(mutate).toHaveBeenCalledWith('/peers/requests/conn-1/respond', { accept: false })
    );
    await waitFor(() =>
      expect(screen.getByText('settings.peers.requests.declined')).toBeInTheDocument()
    );
  });

  it('keeps the chips actionable when the response fails', async () => {
    mutate.mockRejectedValueOnce(new ApiError('gone', 404, { detail: 'peers_not_found' }));
    const { user } = renderWithProviders(<PeerMessageActions metadata={REQUEST_META} />);
    await user.click(screen.getByRole('button', { name: /settings.peers.requests.accept/ }));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(screen.getByRole('button', { name: /settings.peers.requests.accept/ })).toBeEnabled();
  });
});
