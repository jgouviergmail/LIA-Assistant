/**
 * AdminUsersSection — the admin user table: loading vs loaded, a silently
 * ignored aborted fetch vs a reported failure, the activate/deactivate flow
 * (reason prompt, cancellation, success and rollback-on-error), the two
 * destructive paths (soft delete then GDPR erase, each confirm-gated, with the
 * optimistic removal reverting when the server refuses), the superuser
 * exemption, and sort-driven refetching.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { AdminUserRow } from '../AdminUsersSection';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { get } }));
const { toggleUserActive, deleteUserAccount, deleteUserGDPR } = vi.hoisted(() => ({
  toggleUserActive: vi.fn(),
  deleteUserAccount: vi.fn(),
  deleteUserGDPR: vi.fn(),
}));
vi.mock('@/lib/actions/settings-actions', () => ({
  toggleUserActive,
  deleteUserAccount,
  deleteUserGDPR,
}));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import AdminUsersSection from '../AdminUsersSection';

const ACT = {
  deactivate: 'settings.admin.users.actions.deactivate',
  activate: 'settings.admin.users.actions.activate',
  delete: 'settings.admin.users.actions.delete',
  erase: 'settings.admin.users.actions.erase',
};

function adminUser(over: Partial<AdminUserRow> = {}): AdminUserRow {
  return {
    id: 'u1',
    email: 'alice@example.com',
    full_name: 'Alice',
    is_active: true,
    is_verified: true,
    is_superuser: false,
    created_at: '2026-01-01T00:00:00Z',
    language: 'en',
    personality_id: null,
    voice_enabled: false,
    memory_enabled: true,
    tokens_display_enabled: false,
    last_login: null,
    last_message_at: null,
    total_messages: 0,
    total_tokens: 0,
    tokens_in: 0,
    tokens_out: 0,
    tokens_cache: 0,
    total_cost_eur: 0,
    total_google_api_requests: 0,
    cycle_messages: 0,
    cycle_tokens: 0,
    cycle_google_api_requests: 0,
    cycle_cost_eur: 0,
    active_connectors_count: 0,
    memories_count: 0,
    interests_count: 0,
    skills_count: 0,
    mcp_servers_count: 0,
    scheduled_actions_count: 0,
    rag_spaces_count: 0,
    is_usage_blocked: false,
    deleted_at: null,
    is_deleted: false,
    ...over,
  };
}

function page(users: AdminUserRow[]) {
  return { users, total: users.length, page: 1, page_size: 20, total_pages: 1 };
}

function render() {
  return renderWithProviders(<AdminUsersSection lng="en" collapsible={false} />);
}

/** Renders and waits for the first fetch to settle into the table. */
async function renderLoaded(users: AdminUserRow[]) {
  get.mockResolvedValue(page(users));
  const utils = render();
  await screen.findByRole('table');
  return utils;
}

beforeEach(() => {
  vi.clearAllMocks();
  get.mockResolvedValue(page([adminUser()]));
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('AdminUsersSection — loading & fetch failures', () => {
  it('holds the table back until the first page resolves', async () => {
    let release: (value: unknown) => void = () => {};
    get.mockReturnValue(
      new Promise(resolve => {
        release = resolve;
      })
    );
    render();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    release(page([adminUser()]));
    expect(await screen.findByRole('table')).toBeInTheDocument();
  });

  it('lists the returned users', async () => {
    await renderLoaded([adminUser(), adminUser({ id: 'u2', email: 'bob@example.com' })]);
    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
    expect(screen.getByText('bob@example.com')).toBeInTheDocument();
  });

  it('reports a genuine fetch failure', async () => {
    get.mockRejectedValue(new Error('500'));
    render();
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('settings.admin.users.errors.loading')
    );
  });

  it('stays silent when the request was aborted (superseded, not a failure)', async () => {
    const aborted = Object.assign(new Error('canceled'), { name: 'AbortError' });
    get.mockRejectedValue(aborted);
    render();
    // Give the rejection a chance to propagate before asserting the absence.
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(toast.error).not.toHaveBeenCalled();
  });
});

describe('AdminUsersSection — activate / deactivate', () => {
  it('aborts the deactivation when the reason prompt is dismissed', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue(null);
    const { user } = await renderLoaded([adminUser({ is_active: true })]);
    await user.click(screen.getByRole('button', { name: `${ACT.deactivate} alice@example.com` }));
    expect(toggleUserActive).not.toHaveBeenCalled();
  });

  it('deactivates with the captured reason and confirms', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue('spam');
    toggleUserActive.mockResolvedValue({ success: true, message: 'deactivated' });
    const { user } = await renderLoaded([adminUser({ is_active: true })]);
    await user.click(screen.getByRole('button', { name: `${ACT.deactivate} alice@example.com` }));
    await waitFor(() => expect(toggleUserActive).toHaveBeenCalledWith('u1', false, 'spam'));
    expect(toast.success).toHaveBeenCalledWith('deactivated');
  });

  it('activates without asking for a reason', async () => {
    const promptSpy = vi.spyOn(window, 'prompt');
    toggleUserActive.mockResolvedValue({ success: true, message: 'activated' });
    const { user } = await renderLoaded([adminUser({ is_active: false })]);
    await user.click(screen.getByRole('button', { name: `${ACT.activate} alice@example.com` }));
    await waitFor(() => expect(toggleUserActive).toHaveBeenCalledWith('u1', true, null));
    expect(promptSpy).not.toHaveBeenCalled();
  });

  it('reports the server refusal so the optimistic toggle rolls back', async () => {
    toggleUserActive.mockResolvedValue({ success: false, error: 'not allowed' });
    const { user } = await renderLoaded([adminUser({ is_active: false })]);
    await user.click(screen.getByRole('button', { name: `${ACT.activate} alice@example.com` }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('not allowed'));
    // React reverts the optimistic toggle when the transition settles, which can
    // land after the toast — wait for the confirmed state rather than sampling it.
    expect(
      await screen.findByRole('button', { name: `${ACT.activate} alice@example.com` })
    ).toBeInTheDocument();
  });
});

describe('AdminUsersSection — destructive paths', () => {
  const deactivated = adminUser({ is_active: false });

  it('does not delete when the confirmation is dismissed', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const { user } = await renderLoaded([deactivated]);
    await user.click(screen.getByRole('button', { name: `${ACT.delete} alice@example.com` }));
    expect(deleteUserAccount).not.toHaveBeenCalled();
  });

  it('soft-deletes a deactivated user and switches the row to the erase affordance', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    deleteUserAccount.mockResolvedValue({ success: true, message: 'deleted' });
    const { user } = await renderLoaded([deactivated]);
    await user.click(screen.getByRole('button', { name: `${ACT.delete} alice@example.com` }));
    await waitFor(() => expect(deleteUserAccount).toHaveBeenCalledWith('u1'));
    expect(toast.success).toHaveBeenCalledWith('deleted');
    // Soft-deleted rows expose GDPR erase instead of delete.
    expect(
      await screen.findByRole('button', { name: `${ACT.erase} alice@example.com` })
    ).toBeInTheDocument();
  });

  it('reports a failed soft delete', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    deleteUserAccount.mockResolvedValue({ success: false, error: 'still active' });
    const { user } = await renderLoaded([deactivated]);
    await user.click(screen.getByRole('button', { name: `${ACT.delete} alice@example.com` }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('still active'));
  });

  it('erases a soft-deleted user, removing the row', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    deleteUserGDPR.mockResolvedValue({ success: true, message: 'erased' });
    const { user } = await renderLoaded([adminUser({ is_deleted: true, is_active: false })]);
    await user.click(screen.getByRole('button', { name: `${ACT.erase} alice@example.com` }));
    await waitFor(() => expect(deleteUserGDPR).toHaveBeenCalledWith('u1'));
    await waitFor(() => expect(screen.queryByText('alice@example.com')).not.toBeInTheDocument());
    expect(toast.success).toHaveBeenCalledWith('erased');
  });

  it('rolls the optimistic removal back when the erase is refused', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    deleteUserGDPR.mockResolvedValue({ success: false, error: 'nope' });
    const { user } = await renderLoaded([adminUser({ is_deleted: true, is_active: false })]);
    await user.click(screen.getByRole('button', { name: `${ACT.erase} alice@example.com` }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('nope'));
    // React reverts the optimistic delete: the row is back.
    expect(await screen.findByText('alice@example.com')).toBeInTheDocument();
  });

  it('never offers delete or erase for a superuser', async () => {
    await renderLoaded([adminUser({ is_superuser: true, is_active: false, is_deleted: true })]);
    expect(
      screen.queryByRole('button', { name: `${ACT.delete} alice@example.com` })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: `${ACT.erase} alice@example.com` })
    ).not.toBeInTheDocument();
  });
});

describe('AdminUsersSection — sorting', () => {
  it('refetches with the chosen sort column and marks the header', async () => {
    const { user } = await renderLoaded([adminUser()]);
    await user.click(screen.getByRole('columnheader', { name: /table\.email/ }));
    await waitFor(() =>
      expect(get).toHaveBeenLastCalledWith(
        '/users/admin/search',
        expect.objectContaining({
          params: expect.objectContaining({ sort_by: 'email', sort_order: 'asc' }),
        })
      )
    );
    expect(screen.getByRole('columnheader', { name: /table\.email/ })).toHaveAttribute(
      'aria-sort',
      'ascending'
    );
  });
});
