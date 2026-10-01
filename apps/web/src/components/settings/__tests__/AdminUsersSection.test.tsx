/**
 * AdminUsersSection — the admin user table: loading vs loaded, a silently
 * ignored aborted fetch vs a reported failure, the activate/deactivate flow
 * (reason prompt, cancellation, success and rollback-on-error), the two
 * destructive paths (soft delete then GDPR erase, each confirm-gated, with the
 * optimistic removal reverting when the server refuses), the superuser
 * exemption, and sort-driven refetching.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import {
  answerConfirmDialog,
  renderWithProviders,
  screen,
  waitFor,
  within,
} from '@/__tests__/test-utils';
import type { AdminUserRow } from '../AdminUsersSection';
import type { AdminUserSwitch } from '../admin-users/columns';

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

/** Every switch, most of them off — the table must render each one. */
const SWITCHES: Record<AdminUserSwitch, boolean> = {
  memory_enabled: true,
  psyche_enabled: false,
  psyche_display_avatar: false,
  habits_enabled: false,
  journals_enabled: false,
  journal_consolidation_enabled: false,
  journal_consolidation_with_history: false,
  voice_enabled: false,
  voice_mode_enabled: false,
  phone_rich_context_enabled: false,
  heartbeat_enabled: false,
  interests_enabled: false,
  relation_debrief_enabled: false,
  image_generation_enabled: false,
  image_generation_prompt_enhancement: false,
  discovery_enabled: false,
  peer_email_visible: false,
  use_last_known_location: false,
  login_notifications_enabled: false,
  health_metrics_agents_enabled: false,
  tokens_display_enabled: false,
  debug_panel_enabled: false,
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
    ...SWITCHES,
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
  return renderWithProviders(<AdminUsersSection lng="en" />);
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
    const row = screen.getByRole('row', { name: /alice@example\.com/ });
    await user.click(
      within(row).getByRole('button', { name: `${ACT.activate} alice@example.com` })
    );
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('not allowed'));
    // React reverts the optimistic toggle when the transition settles, which can
    // land after the toast — wait for the confirmed state rather than sampling it.
    // Polled inside the row: a role query weighs every element it scans, and the
    // table carries a column per switch (measured: the page-wide poll overran its
    // second under the coverage run, twice out of two).
    expect(
      await within(row).findByRole('button', { name: `${ACT.activate} alice@example.com` })
    ).toBeInTheDocument();
  });
});

describe('AdminUsersSection — destructive paths', () => {
  const deactivated = adminUser({ is_active: false });

  it('does not delete when the confirmation is dismissed', async () => {
    const { user } = await renderLoaded([deactivated]);
    await user.click(screen.getByRole('button', { name: `${ACT.delete} alice@example.com` }));
    await answerConfirmDialog(user, false);
    expect(deleteUserAccount).not.toHaveBeenCalled();
  });

  it('soft-deletes a deactivated user and switches the row to the erase affordance', async () => {
    deleteUserAccount.mockResolvedValue({ success: true, message: 'deleted' });
    const { user } = await renderLoaded([deactivated]);
    await user.click(screen.getByRole('button', { name: `${ACT.delete} alice@example.com` }));
    await answerConfirmDialog(user);
    await waitFor(() => expect(deleteUserAccount).toHaveBeenCalledWith('u1'));
    expect(toast.success).toHaveBeenCalledWith('deleted');
    // Soft-deleted rows expose GDPR erase instead of delete.
    expect(
      await screen.findByRole('button', { name: `${ACT.erase} alice@example.com` })
    ).toBeInTheDocument();
  });

  it('reports a failed soft delete', async () => {
    deleteUserAccount.mockResolvedValue({ success: false, error: 'still active' });
    const { user } = await renderLoaded([deactivated]);
    await user.click(screen.getByRole('button', { name: `${ACT.delete} alice@example.com` }));
    await answerConfirmDialog(user);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('still active'));
  });

  it('erases a soft-deleted user, removing the row', async () => {
    deleteUserGDPR.mockResolvedValue({ success: true, message: 'erased' });
    const { user } = await renderLoaded([adminUser({ is_deleted: true, is_active: false })]);
    await user.click(screen.getByRole('button', { name: `${ACT.erase} alice@example.com` }));
    await answerConfirmDialog(user);
    await waitFor(() => expect(deleteUserGDPR).toHaveBeenCalledWith('u1'));
    await waitFor(() => expect(screen.queryByText('alice@example.com')).not.toBeInTheDocument());
    expect(toast.success).toHaveBeenCalledWith('erased');
  });

  it('rolls the optimistic removal back when the erase is refused', async () => {
    deleteUserGDPR.mockResolvedValue({ success: false, error: 'nope' });
    const { user } = await renderLoaded([adminUser({ is_deleted: true, is_active: false })]);
    await user.click(screen.getByRole('button', { name: `${ACT.erase} alice@example.com` }));
    await answerConfirmDialog(user);
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
    await user.click(screen.getByRole('button', { name: /table\.email/ }));
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

describe('AdminUsersSection — columns', () => {
  /** The header names in order, and the body cells of the first row. */
  async function grid(users: AdminUserRow[]) {
    await renderLoaded(users);
    // The sort arrow is `aria-hidden` but still text: the NAME is what matters.
    const headers = screen
      .getAllByRole('columnheader')
      .map(header => (header.textContent ?? '').replace(/[↑↓]/g, ''));
    const cells = within(screen.getAllByRole('row')[1]).getAllByRole('cell');
    return { headers, cells };
  }

  it('lays the columns out: identity, sign-up, status, counts, usage — then every switch', async () => {
    const { headers } = await grid([adminUser()]);

    expect(headers.slice(0, 3)).toEqual([
      'settings.admin.users.table.email',
      'settings.admin.users.table.name',
      'settings.admin.users.table.registered',
    ]);
    const lastStat = headers.indexOf('settings.admin.users.table.cost_period');
    const switches = headers.slice(lastStat + 1);
    expect(switches).toHaveLength(Object.keys(SWITCHES).length);
    expect(switches.every(name => name.startsWith('settings.admin.users.switches.'))).toBe(true);
    expect(headers).not.toContain('settings.admin.users.table.voice');
  });

  it('shows the sign-up date as a machine-readable date', async () => {
    const { cells } = await grid([adminUser({ created_at: '2025-03-14T09:30:00Z' })]);

    const time = cells[2].querySelector('time');
    expect(time).toHaveAttribute('dateTime', '2025-03-14T09:30:00Z');
    expect(time?.textContent).toMatch(/2025/);
  });

  it('spells each switch state out for a screen reader, not by colour alone', async () => {
    const { headers, cells } = await grid([
      adminUser({ heartbeat_enabled: true, debug_panel_enabled: false }),
    ]);

    const on = headers.indexOf('settings.admin.users.switches.heartbeat_enabled');
    const off = headers.indexOf('settings.admin.users.switches.debug_panel_enabled');
    expect(cells[on]).toHaveTextContent('settings.admin.users.state_on');
    expect(cells[off]).toHaveTextContent('settings.admin.users.state_off');
    expect(cells[off]).toHaveTextContent('—');
  });

  it('sorts by a switch from the keyboard', async () => {
    const { user } = await renderLoaded([adminUser()]);
    const header = screen.getByRole('button', {
      name: 'settings.admin.users.switches.heartbeat_enabled',
    });

    header.focus();
    await user.keyboard('{Enter}');

    await waitFor(() =>
      expect(get).toHaveBeenLastCalledWith(
        '/users/admin/search',
        expect.objectContaining({
          params: expect.objectContaining({ sort_by: 'heartbeat_enabled', sort_order: 'asc' }),
        })
      )
    );
    expect(
      screen.getByRole('columnheader', { name: 'settings.admin.users.switches.heartbeat_enabled' })
    ).toHaveAttribute('aria-sort', 'ascending');
  });

  it('names every icon column in a legend a touch screen can read', async () => {
    const { user } = await renderLoaded([adminUser()]);

    await user.click(screen.getByText('settings.admin.users.legend_title'));

    const entries = within(screen.getByRole('list')).getAllByRole('listitem');
    // The blocked flag, the seven counts and every switch.
    expect(entries).toHaveLength(1 + 7 + Object.keys(SWITCHES).length);
    expect(entries.map(entry => entry.textContent)).toContain(
      'settings.admin.users.switches.heartbeat_enabled'
    );
  });
});
