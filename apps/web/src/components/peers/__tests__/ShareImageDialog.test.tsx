/**
 * ShareImageDialog — picking a connection, an optional comment, one confirmation.
 *
 * What is pinned: the three states that must not be confused (loading, a read
 * that failed, no connection yet), the dialog's own button as the only way to
 * send, the payload the API receives (the comment trimmed, or null), the
 * published bound on the comment, and every refusal reaching the reader in
 * their words, never as a raw code.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { ConnectionView } from '@/hooks/usePeerConnections';
import { ApiError } from '@/lib/api-client';

const { recipientsState } = vi.hoisted(() => ({ recipientsState: vi.fn() }));
vi.mock('@/hooks/usePeerRecipients', () => ({ usePeerRecipientsState: recipientsState }));

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { post },
}));

const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { ShareImageDialog } from '../ShareImageDialog';

type Peer = Pick<ConnectionView, 'id' | 'peer_display_name'>;

const PEERS: Peer[] = [
  { id: 'c1', peer_display_name: 'Gérard Dupont' },
  { id: 'c2', peer_display_name: 'Claire Lefèvre' },
];

function state(over: Partial<{ recipients: Peer[]; loading: boolean; error: Error | null }>) {
  return { recipients: PEERS, loading: false, error: null, ...over };
}

function renderDialog(onOpenChange = vi.fn()) {
  const rendered = renderWithProviders(
    <ShareImageDialog
      open
      onOpenChange={onOpenChange}
      attachmentId="att-1"
      imageTitle="a lighthouse at dusk"
    />
  );
  return { ...rendered, onOpenChange };
}

const submit = () => screen.getByRole('button', { name: 'settings.peers.share_image.submit' });

beforeEach(() => {
  vi.clearAllMocks();
  recipientsState.mockReturnValue(state({}));
  post.mockResolvedValue({ id: 's1', recipient_display_name: 'Claire Lefèvre', delivered: true });
});

describe('ShareImageDialog — who can receive it', () => {
  it('says it is loading, never that there is nobody', () => {
    recipientsState.mockReturnValue(state({ recipients: [], loading: true }));
    renderDialog();

    expect(screen.getByRole('status')).toHaveTextContent('settings.peers.recipients.loading');
    expect(screen.queryByText(/no_connection/)).not.toBeInTheDocument();
  });

  it('says the read failed, never that there is nobody', () => {
    recipientsState.mockReturnValue(state({ recipients: [], error: new Error('503') }));
    renderDialog();

    expect(screen.getByRole('alert')).toHaveTextContent('settings.peers.recipients.load_error');
  });

  it('points to the settings when there is truly nobody yet', () => {
    recipientsState.mockReturnValue(state({ recipients: [] }));
    renderDialog();

    expect(screen.getByText(/settings.peers.recipients.no_connection/)).toBeInTheDocument();
    expect(submit()).toBeDisabled();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('lists the connections as one radio group, named by its legend', () => {
    renderDialog();

    const group = screen.getByRole('group', { name: 'settings.peers.share_image.recipient' });
    expect(group).toBeInTheDocument();
    expect(screen.getAllByRole('radio')).toHaveLength(2);
    expect(screen.getByRole('radio', { name: 'Gérard Dupont' })).not.toBeChecked();
  });
});

describe('ShareImageDialog — sending', () => {
  it('sends nothing until someone is picked', () => {
    renderDialog();

    expect(submit()).toBeDisabled();
    expect(post).not.toHaveBeenCalled();
  });

  it('sends the image and the trimmed comment, then closes', async () => {
    const { user, onOpenChange } = renderDialog();

    await user.click(screen.getByRole('radio', { name: 'Claire Lefèvre' }));
    await user.type(screen.getByRole('textbox'), '  Pour toi !  ');
    await user.click(submit());

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/peers/connections/c2/images', {
        attachment_id: 'att-1',
        comment: 'Pour toi !',
      })
    );
    expect(toast.success).toHaveBeenCalledWith('settings.peers.share_image.shared', undefined);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('sends no comment as null', async () => {
    const { user } = renderDialog();

    await user.click(screen.getByRole('radio', { name: 'Gérard Dupont' }));
    await user.click(submit());

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/peers/connections/c1/images', {
        attachment_id: 'att-1',
        comment: null,
      })
    );
  });

  it('says when only the notification failed', async () => {
    post.mockResolvedValue({ id: 's1', recipient_display_name: 'Claire', delivered: false });
    const { user } = renderDialog();

    await user.click(screen.getByRole('radio', { name: 'Claire Lefèvre' }));
    await user.click(submit());

    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('settings.peers.share_image.shared', {
        description: 'settings.peers.share_image.not_notified',
      })
    );
  });

  it('turns a refusal into the reader’s words and stays open', async () => {
    post.mockRejectedValue(
      new ApiError('Too Many Requests', 429, { detail: 'peers_image_quota_reached' })
    );
    const { user, onOpenChange } = renderDialog();

    await user.click(screen.getByRole('radio', { name: 'Claire Lefèvre' }));
    await user.click(submit());

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('settings.peers.errors.image_quota_reached')
    );
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it('can be driven from the keyboard', async () => {
    const { user } = renderDialog();

    screen.getByRole('radio', { name: 'Gérard Dupont' }).focus();
    await user.keyboard(' ');
    expect(screen.getByRole('radio', { name: 'Gérard Dupont' })).toBeChecked();
    submit().focus();
    await user.keyboard('{Enter}');

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  });
});

describe('ShareImageDialog — the comment', () => {
  it('publishes the bound the API enforces and counts what was typed', async () => {
    const { user } = renderDialog();

    const box = screen.getByRole('textbox');
    expect(box).toHaveAttribute('maxLength', '500');
    await user.type(box, 'abc');
    expect(box).toHaveAccessibleDescription('settings.peers.share_image.characters');
  });
});
