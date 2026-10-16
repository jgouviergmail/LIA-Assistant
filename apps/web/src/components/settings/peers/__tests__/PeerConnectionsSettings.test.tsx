/**
 * PeerConnectionsSettings — the section shell: discovery master toggle,
 * composition of the five blocks, result-driven toasts with mapped codes.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act } from '@testing-library/react';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { usePeerConnections } = vi.hoisted(() => ({ usePeerConnections: vi.fn() }));
vi.mock('@/hooks/usePeerConnections', () => ({ usePeerConnections }));
const { useAppConfig } = vi.hoisted(() => ({ useAppConfig: vi.fn() }));
vi.mock('@/hooks/useAppConfig', () => ({ useAppConfig }));
const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/components/ui/use-confirm', () => ({
  useConfirm: () => ({ confirm: vi.fn().mockResolvedValue(true), confirmDialog: null }),
}));

import { PeerConnectionsSettings } from '../../PeerConnectionsSettings';

function hookState(over: Record<string, unknown> = {}) {
  return {
    discoveryEnabled: false,
    requests: [],
    connections: [],
    blocks: [],
    accessLog: [],
    error: null,
    hasCompleteData: true,
    loading: false,
    initialLoading: false,
    mutating: false,
    emailVisible: false,
    setDiscovery: vi.fn().mockResolvedValue({ ok: true, errorCode: null }),
    setEmailVisible: vi.fn().mockResolvedValue({ ok: true, errorCode: null }),
    search: vi.fn().mockResolvedValue({ matches: [], errorCode: null }),
    sendRequest: vi.fn().mockResolvedValue({ ok: true, errorCode: null }),
    respond: vi.fn().mockResolvedValue({ ok: true, errorCode: null }),
    removeConnection: vi.fn().mockResolvedValue({ ok: true, errorCode: null }),
    setShare: vi.fn().mockResolvedValue({ ok: true, errorCode: null }),
    block: vi.fn().mockResolvedValue({ ok: true, errorCode: null }),
    unblock: vi.fn().mockResolvedValue({ ok: true, errorCode: null }),
    refetchAll: vi.fn(),
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  useAppConfig.mockReturnValue({
    config: { features: { peers_enabled: true } },
    loading: false,
    error: null,
  });
  useAuth.mockReturnValue({ user: { id: 'one', full_name: 'Marie Dupont' } });
});

describe('PeerConnectionsSettings', () => {
  it('renders NOTHING and disables the queries when the instance flag is off', () => {
    useAppConfig.mockReturnValue({
      config: { features: { peers_enabled: false } },
      loading: false,
      error: null,
    });
    usePeerConnections.mockReturnValue(hookState());
    const { container } = renderWithProviders(<PeerConnectionsSettings lng="fr" />);
    expect(container).toBeEmptyDOMElement();
    expect(usePeerConnections).toHaveBeenCalledWith(false);
  });

  it('keeps exact discovery visible while permissions and requests remain separate folds', async () => {
    usePeerConnections.mockReturnValue(hookState());
    const { user, container } = renderWithProviders(<PeerConnectionsSettings lng="fr" />);
    const commandTitles = [...container.querySelectorAll('summary')]
      .slice(0, 3)
      .map(node => node.textContent?.replace(/0$/, ''));
    expect(commandTitles).toEqual([
      'settings.peers.visibility_title',
      'settings.peers.blocks.title',
      'settings.peers.access_log.title',
    ]);
    const search = screen.getByRole('textbox', { name: 'settings.peers.discovery.search_label' });
    expect(search).toBeVisible();
    expect(screen.queryByRole('switch')).toBeNull();
    await user.click(screen.getByText('settings.peers.requests.title'));
    expect(screen.getByText('settings.peers.requests.empty')).toBeInTheDocument();
    expect(search).toBeVisible();
    await user.click(screen.getByText('settings.peers.visibility_title'));
    expect(
      screen.getByRole('switch', { name: 'settings.peers.discovery.toggle_label' })
    ).toBeInTheDocument();
    expect(search).toBeVisible();
  });

  it('retries a failed first read instead of claiming there are no connections', async () => {
    const refetchAll = vi.fn().mockRejectedValue(new Error('unavailable'));
    usePeerConnections.mockReturnValue(
      hookState({
        error: new Error('unavailable'),
        hasCompleteData: false,
        refetchAll,
      })
    );
    const { user } = renderWithProviders(<PeerConnectionsSettings lng="fr" />);
    expect(screen.getByRole('alert')).toHaveTextContent('settings.peers.load_error');
    expect(screen.queryByText('settings.peers.connections.empty')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'common.retry' }));
    expect(refetchAll).toHaveBeenCalledOnce();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'common.retry' })).toHaveAttribute(
        'aria-disabled',
        'false'
      )
    );
  });

  it('retains loaded identities during a failed background reread', () => {
    usePeerConnections.mockReturnValue(hookState({ error: new Error('unavailable') }));
    renderWithProviders(<PeerConnectionsSettings lng="fr" />);
    expect(screen.getByRole('alert')).toBeVisible();
    expect(
      screen.getByRole('textbox', { name: 'settings.peers.discovery.search_label' })
    ).toBeVisible();
  });

  it('does not toast a late mutation result to a different signed-in account', async () => {
    let finish: (value: { ok: boolean; errorCode: null }) => void = () => {};
    const setDiscovery = vi.fn().mockImplementation(
      () =>
        new Promise(done => {
          finish = done;
        })
    );
    usePeerConnections.mockReturnValue(hookState({ setDiscovery }));
    const { user, rerender } = renderWithProviders(<PeerConnectionsSettings lng="fr" />);
    await user.click(screen.getByText('settings.peers.visibility_title'));
    await user.click(screen.getByRole('switch', { name: 'settings.peers.discovery.toggle_label' }));
    useAuth.mockReturnValue({ user: { id: 'two', full_name: 'Nouveau compte' } });
    usePeerConnections.mockReturnValue(hookState());
    rerender(<PeerConnectionsSettings lng="fr" />);
    await act(async () => {
      finish({ ok: true, errorCode: null });
    });
    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
    expect(screen.queryByText('Marie Dupont')).not.toBeInTheDocument();
  });

  it('clears local discovery text and ignores a delayed result after account replacement', async () => {
    let finish: (value: { matches: unknown[]; errorCode: null }) => void = () => {};
    const search = vi.fn().mockImplementation(
      () =>
        new Promise(done => {
          finish = done;
        })
    );
    usePeerConnections.mockReturnValue(hookState({ search }));
    const { user, rerender } = renderWithProviders(<PeerConnectionsSettings lng="fr" />);
    const input = screen.getByRole('textbox', { name: 'settings.peers.discovery.search_label' });
    await user.type(input, 'Identité privée');
    await user.keyboard('{Enter}');
    useAuth.mockReturnValue({ user: { id: 'two', full_name: 'Nouveau compte' } });
    usePeerConnections.mockReturnValue(hookState());
    rerender(<PeerConnectionsSettings lng="fr" />);
    await act(async () => {
      finish({
        matches: [
          {
            peer_id: 'private',
            display_name: 'Ancien résultat privé',
            email_hint: 'x…@test',
            relationship: 'none',
          },
        ],
        errorCode: null,
      });
    });
    expect(
      screen.getByRole('textbox', { name: 'settings.peers.discovery.search_label' })
    ).toHaveValue('');
    expect(screen.queryByText('Ancien résultat privé')).not.toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('surfaces the searchable own name with a one-click copy (Lot 7)', async () => {
    usePeerConnections.mockReturnValue(hookState());
    const { user } = renderWithProviders(<PeerConnectionsSettings lng="fr" />);
    await user.click(screen.getByText('settings.peers.visibility_title'));
    expect(screen.getByText('Marie Dupont')).toBeInTheDocument();
    expect(screen.getByText('settings.peers.my_name.hint')).toBeInTheDocument();
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined);
    await user.click(screen.getByRole('button', { name: 'settings.peers.my_name.copy' }));
    expect(writeText).toHaveBeenCalledWith('Marie Dupont');
  });

  it('waits for actual clipboard success before displaying the copied checkmark', async () => {
    usePeerConnections.mockReturnValue(hookState());
    const { user } = renderWithProviders(<PeerConnectionsSettings lng="fr" />);
    await user.click(screen.getByText('settings.peers.visibility_title'));
    let finish: () => void = () => {};
    vi.spyOn(navigator.clipboard, 'writeText').mockImplementation(
      () =>
        new Promise<void>(resolve => {
          finish = resolve;
        })
    );
    const copy = screen.getByRole('button', { name: 'settings.peers.my_name.copy' });
    await user.click(copy);
    expect(copy.querySelector('.lucide-check')).toBeNull();
    expect(copy).toHaveAttribute('aria-busy', 'true');
    await act(async () => {
      finish();
    });
    expect(copy.querySelector('.lucide-check')).not.toBeNull();
    expect(copy).toHaveFocus();
  });

  it('shows a copy failure without a success checkmark when the clipboard rejects access', async () => {
    usePeerConnections.mockReturnValue(hookState());
    const { user } = renderWithProviders(<PeerConnectionsSettings lng="fr" />);
    await user.click(screen.getByText('settings.peers.visibility_title'));
    vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('denied'));
    const copy = screen.getByRole('button', { name: 'settings.peers.my_name.copy' });
    await user.click(copy);
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('common.copyFailed'));
    expect(copy.querySelector('.lucide-check')).toBeNull();
    expect(copy).toHaveFocus();
  });

  it('says plainly that an empty profile name makes the user unfindable', async () => {
    useAuth.mockReturnValue({ user: { id: 'one', full_name: null } });
    usePeerConnections.mockReturnValue(hookState());
    const { user } = renderWithProviders(<PeerConnectionsSettings lng="fr" />);
    await user.click(screen.getByText('settings.peers.visibility_title'));
    expect(screen.getByText('settings.peers.my_name.missing')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'settings.peers.my_name.copy' })).toBeNull();
  });

  it('toggling discovery persists and toasts success', async () => {
    const setDiscovery = vi.fn().mockResolvedValue({ ok: true, errorCode: null });
    usePeerConnections.mockReturnValue(hookState({ setDiscovery }));
    const { user } = renderWithProviders(<PeerConnectionsSettings lng="fr" />);
    await user.click(screen.getByText('settings.peers.visibility_title'));
    await user.click(screen.getByRole('switch', { name: 'settings.peers.discovery.toggle_label' }));
    expect(setDiscovery).toHaveBeenCalledWith(true);
    await waitFor(() => expect(toast.success).toHaveBeenCalledTimes(1));
  });

  it('the discovery switch keeps its focus and refuses a second submit while saving', async () => {
    // A control disabled *while focused* is blurred by the browser and leaves
    // the tab order — a keyboard user toggling this would land back on <body>.
    // aria-disabled announces the state without that cost; the handler guard
    // is what actually prevents the double submit.
    const setDiscovery = vi.fn().mockResolvedValue({ ok: true, errorCode: null });
    usePeerConnections.mockReturnValue(hookState({ mutating: true, setDiscovery }));
    const { user } = renderWithProviders(<PeerConnectionsSettings lng="fr" />);
    await user.click(screen.getByText('settings.peers.visibility_title'));

    const toggle = screen.getByRole('switch', { name: 'settings.peers.discovery.toggle_label' });
    await user.click(toggle);

    expect(setDiscovery).not.toHaveBeenCalled();
    expect(toggle).toHaveAttribute('aria-disabled', 'true');
    expect(toggle).not.toBeDisabled();
    expect(toggle).toHaveFocus();
  });

  it('a failed action toasts the MAPPED backend code', async () => {
    const respond = vi.fn().mockResolvedValue({ ok: false, errorCode: 'peers_not_pending' });
    usePeerConnections.mockReturnValue(
      hookState({
        respond,
        requests: [
          {
            id: 'conn-1',
            peer_id: 'p1',
            peer_display_name: 'Marie Dupont',
            peer_email_hint: 'm…@g….com',
            peer_email: null,
            status: 'pending',
            direction: 'incoming',
            requested_at: '2026-07-29T08:00:00Z',
            responded_at: null,
            context_message: null,
            my_shares: [],
            their_shares: [],
          },
        ],
      })
    );
    const { user } = renderWithProviders(<PeerConnectionsSettings lng="fr" />);
    await user.click(screen.getByText('settings.peers.requests.title'));
    await user.click(screen.getByRole('button', { name: 'settings.peers.requests.accept' }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('settings.peers.errors.not_pending')
    );
  });

  it('renders a loading placeholder while the FIRST load runs', () => {
    usePeerConnections.mockReturnValue(
      hookState({ loading: true, initialLoading: true, discoveryEnabled: null })
    );
    renderWithProviders(<PeerConnectionsSettings lng="fr" />);
    expect(screen.getByText('settings.peers.title')).toBeInTheDocument();
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
  });

  it('a REFETCH never unmounts the section — it only marks it busy', async () => {
    // Regression guard: swapping the subtree for a spinner on every refetch
    // wiped the search box under the user (and lost their keyboard focus)
    // each time any mutation succeeded.
    usePeerConnections.mockReturnValue(hookState({ loading: true, initialLoading: false }));
    const { user } = renderWithProviders(<PeerConnectionsSettings lng="fr" />);
    await user.click(screen.getByText('settings.peers.visibility_title'));
    const input = screen.getByRole('textbox', {
      name: 'settings.peers.discovery.search_label',
    });
    await user.type(input, 'marie@exemple.fr');

    expect(input).toHaveValue('marie@exemple.fr');
    expect(input).toHaveFocus();
    const toggle = screen.getByRole('switch', {
      name: 'settings.peers.discovery.toggle_label',
    });
    expect(toggle).toBeInTheDocument();
    expect(toggle.closest('[aria-busy="true"]')).not.toBeNull();
  });

  it('the address-visibility switch is a SEPARATE consent from discovery', async () => {
    // ADR-189: being findable and handing your address over are two different
    // decisions. The verb sends only its own field, so one toggle can never
    // revert the other by echoing a stale value.
    const setEmailVisible = vi.fn().mockResolvedValue({ ok: true, errorCode: null });
    const setDiscovery = vi.fn().mockResolvedValue({ ok: true, errorCode: null });
    usePeerConnections.mockReturnValue(hookState({ setEmailVisible, setDiscovery }));
    const { user } = renderWithProviders(<PeerConnectionsSettings lng="fr" />);
    await user.click(screen.getByText('settings.peers.visibility_title'));

    await user.click(
      screen.getByRole('switch', { name: 'settings.peers.email_visibility.toggle_label' })
    );

    expect(setEmailVisible).toHaveBeenCalledWith(true);
    expect(setDiscovery).not.toHaveBeenCalled();
    await waitFor(() => expect(toast.success).toHaveBeenCalledTimes(1));
  });

  it('lists connection cards for accepted connections', async () => {
    usePeerConnections.mockReturnValue(
      hookState({
        connections: [
          {
            id: 'conn-2',
            peer_id: 'p2',
            peer_display_name: 'Peer Beta',
            peer_email_hint: 'b…@t….local',
            peer_email: null,
            status: 'accepted',
            direction: null,
            requested_at: '2026-07-28T08:00:00Z',
            responded_at: '2026-07-28T09:00:00Z',
            context_message: null,
            my_shares: [],
            their_shares: [],
          },
        ],
      })
    );
    renderWithProviders(<PeerConnectionsSettings lng="fr" />);
    expect(screen.getByText('Peer Beta')).toBeInTheDocument();
    expect(screen.getByText('settings.peers.connections.title')).toBeInTheDocument();
  });
});
