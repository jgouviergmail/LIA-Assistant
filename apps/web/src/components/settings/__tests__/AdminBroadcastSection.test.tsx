/**
 * AdminBroadcastSection — the send gate (a message is mandatory; targeting
 * specific users additionally requires at least one recipient), the mandatory
 * confirmation before a broadcast leaves, the payload actually posted for both
 * targeting modes, recipient add/remove, the inactive-user filter, the form
 * reset after success, and the failure path.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { dataQuery, mutationResult, mutateSpy } from '@/__tests__/api-mocks';
import type { UserAutocompleteItem } from '../AdminBroadcastSection';

// The debounce only gates *when* the query key changes; it has its own unit
// test (hooks/__tests__/useDebounce.test.ts), so collapse it to identity here.
vi.mock('@/hooks/useDebounce', () => ({ useDebounce: (v: unknown) => v }));
const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));
const { useApiMutation } = vi.hoisted(() => ({ useApiMutation: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import AdminBroadcastSection from '../AdminBroadcastSection';

const ENDPOINT = '/notifications/admin/broadcast';
const SEND = 'settings.admin.broadcast.send';
const CONFIRM = 'settings.admin.broadcast.confirm_send';
const MESSAGE_LABEL = 'settings.admin.broadcast.message_label';
const SEARCH = 'settings.admin.broadcast.search_users';

function candidate(over: Partial<UserAutocompleteItem> = {}): UserAutocompleteItem {
  return { id: 'u1', email: 'alice@example.com', full_name: 'Alice', is_active: true, ...over };
}

let sendBroadcast: ReturnType<typeof mutateSpy>;

function stubSearch(users: UserAutocompleteItem[]) {
  useApiQuery.mockReturnValue(dataQuery({ users, total: users.length }));
}

function render() {
  return renderWithProviders(<AdminBroadcastSection lng="en" />);
}

/** Opens the confirmation dialog and validates it. */
async function confirmSend(user: ReturnType<typeof render>['user']) {
  await user.click(screen.getByRole('button', { name: SEND }));
  await screen.findByText('settings.admin.broadcast.confirm_title');
  await user.click(screen.getByRole('button', { name: CONFIRM }));
}

beforeEach(() => {
  vi.clearAllMocks();
  sendBroadcast = mutateSpy().mockResolvedValue({
    success: true,
    broadcast_id: 'b1',
    total_users: 42,
    fcm_sent: 40,
    fcm_failed: 2,
  });
  useApiMutation.mockReturnValue(mutationResult({ mutate: sendBroadcast }));
  stubSearch([]);
});

describe('AdminBroadcastSection — send gate', () => {
  it('refuses to arm the send button without a message', () => {
    render();
    expect(screen.getByRole('button', { name: SEND })).toBeDisabled();
  });

  it('arms the send button once a message is typed (all-users mode)', async () => {
    const { user } = render();
    await user.type(screen.getByLabelText(MESSAGE_LABEL), 'Maintenance tonight');
    expect(screen.getByRole('button', { name: SEND })).toBeEnabled();
  });

  it('keeps the send button locked in targeted mode until a recipient is picked', async () => {
    const { user } = render();
    await user.type(screen.getByLabelText(MESSAGE_LABEL), 'Maintenance tonight');
    await user.click(
      screen.getByRole('button', { name: 'settings.admin.broadcast.selected_users' })
    );
    expect(screen.getByRole('button', { name: SEND })).toBeDisabled();
  });

  it('counts the typed characters', async () => {
    const { user } = render();
    await user.type(screen.getByLabelText(MESSAGE_LABEL), 'abcde');
    expect(screen.getByText('5/1000')).toBeInTheDocument();
  });
});

describe('AdminBroadcastSection — confirmation', () => {
  it('never posts without passing through the confirmation dialog', async () => {
    const { user } = render();
    await user.type(screen.getByLabelText(MESSAGE_LABEL), 'Maintenance tonight');
    await user.click(screen.getByRole('button', { name: SEND }));
    await screen.findByText('settings.admin.broadcast.confirm_title');
    expect(sendBroadcast).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'common.cancel' }));
    expect(sendBroadcast).not.toHaveBeenCalled();
  });

  it('broadcasts to everyone and resets the form on success', async () => {
    const { user } = render();
    const textarea = screen.getByLabelText(MESSAGE_LABEL);
    await user.type(textarea, 'Maintenance tonight');
    await confirmSend(user);
    await waitFor(() =>
      expect(sendBroadcast).toHaveBeenCalledWith(ENDPOINT, {
        message: 'Maintenance tonight',
        expires_in_days: null,
        user_ids: null,
      })
    );
    expect(toast.success).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(textarea).toHaveValue(''));
  });

  it('reports a failed broadcast', async () => {
    sendBroadcast.mockRejectedValue(new Error('boom'));
    const { user } = render();
    await user.type(screen.getByLabelText(MESSAGE_LABEL), 'Maintenance tonight');
    await confirmSend(user);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('settings.admin.broadcast.error'));
  });
});

describe('AdminBroadcastSection — targeted recipients', () => {
  async function pickAlice(user: ReturnType<typeof render>['user']) {
    await user.click(
      screen.getByRole('button', { name: 'settings.admin.broadcast.selected_users' })
    );
    await user.type(screen.getByPlaceholderText(SEARCH), 'al');
    await user.click(await screen.findByRole('button', { name: /Alice/ }));
  }

  it('adds a searched recipient and posts only their id', async () => {
    stubSearch([candidate()]);
    const { user } = render();
    await pickAlice(user);
    await user.type(screen.getByLabelText(MESSAGE_LABEL), 'Targeted note');
    await confirmSend(user);
    await waitFor(() =>
      expect(sendBroadcast).toHaveBeenCalledWith(ENDPOINT, {
        message: 'Targeted note',
        expires_in_days: null,
        user_ids: ['u1'],
      })
    );
  });

  it('removes a picked recipient again', async () => {
    stubSearch([candidate()]);
    const { user } = render();
    await pickAlice(user);
    expect(screen.getByText('settings.admin.broadcast.selected_count')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'settings.admin.broadcast.remove_user' }));
    await waitFor(() =>
      expect(screen.queryByText('settings.admin.broadcast.selected_count')).not.toBeInTheDocument()
    );
  });

  it('never offers an inactive user as a recipient', async () => {
    stubSearch([
      candidate({ id: 'u9', email: 'ghost@example.com', full_name: null, is_active: false }),
    ]);
    const { user } = render();
    await user.click(
      screen.getByRole('button', { name: 'settings.admin.broadcast.selected_users' })
    );
    await user.type(screen.getByPlaceholderText(SEARCH), 'gh');
    expect(await screen.findByText('settings.admin.broadcast.no_users_found')).toBeInTheDocument();
    expect(screen.queryByText('ghost@example.com')).not.toBeInTheDocument();
  });
});
