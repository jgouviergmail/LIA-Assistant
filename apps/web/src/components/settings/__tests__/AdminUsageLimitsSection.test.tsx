/**
 * AdminUsageLimitsSection — the admin usage-limits table: loading / empty /
 * populated, the 404 feature-flag branch that hides the whole section, the
 * generic load failure, the block toggle with its optimistic update and its
 * revert-on-error, the edit modal wiring (open + merge on save), sort-driven
 * refetching, and the debounced search.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { Accordion } from '@/components/ui/accordion';
import { makeUsageLimitsUser } from '@/__tests__/factories';
import type { AdminUserUsageLimitResponse } from '@/types/usage-limits';

const { get, put } = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }));
// Keep the REAL ApiError class (the component branches on `instanceof`); only
// the transport is replaced.
vi.mock('@/lib/api-client', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, apiClient: { get, put } };
});
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));
// The edit modal has its own suite; stub it to a controllable marker so this
// test stays about the section's wiring (open with the right row, merge on save).
vi.mock('@/components/settings/AdminUsageLimitsEditModal', () => ({
  AdminUsageLimitsEditModal: ({
    user,
    onSave,
  }: {
    user: AdminUserUsageLimitResponse;
    onSave: (u?: AdminUserUsageLimitResponse) => void;
  }) => (
    <div>
      <span>modal-for:{user.email}</span>
      <button onClick={() => onSave({ ...user, email: 'merged@example.com' })}>stub-save</button>
    </div>
  ),
}));

import { ApiError } from '@/lib/api-client';
import { AdminUsageLimitsSection } from '../AdminUsageLimitsSection';

const BLOCK = 'usage_limits.table.block';
const UNBLOCK = 'usage_limits.table.unblock';

function listOf(users: AdminUserUsageLimitResponse[]) {
  return { users, total: users.length, page: 1, page_size: 20, total_pages: 1 };
}

function render() {
  return renderWithProviders(
    <Accordion type="multiple" defaultValue={['admin-usage-limits']}>
      <AdminUsageLimitsSection lng="en" />
    </Accordion>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  get.mockResolvedValue(listOf([makeUsageLimitsUser()]));
  put.mockImplementation((_url: string, body: { is_usage_blocked: boolean }) =>
    Promise.resolve(makeUsageLimitsUser({ is_usage_blocked: body.is_usage_blocked }))
  );
});

describe('AdminUsageLimitsSection — table states', () => {
  it('lists the returned rows', async () => {
    await render();
    expect(await screen.findByText('a@b.co')).toBeInTheDocument();
  });

  it('shows the empty state when no user matches', async () => {
    get.mockResolvedValue(listOf([]));
    render();
    expect(await screen.findByText('usage_limits.table.no_results')).toBeInTheDocument();
  });

  it('hides the whole section when the feature is disabled (404)', async () => {
    get.mockRejectedValue(new ApiError('not found', 404));
    render();
    await waitFor(() => expect(get).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByText('usage_limits.title')).not.toBeInTheDocument());
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('reports a non-404 load failure', async () => {
    get.mockRejectedValue(new ApiError('boom', 500));
    render();
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('usage_limits.error.loading'));
    // The section stays mounted — only the data failed.
    expect(screen.getByText('usage_limits.title')).toBeInTheDocument();
  });
});

describe('AdminUsageLimitsSection — block toggle', () => {
  it('blocks a user and keeps the server response', async () => {
    const { user } = render();
    await user.click(await screen.findByRole('button', { name: BLOCK }));
    await waitFor(() =>
      expect(put).toHaveBeenCalledWith('/usage-limits/admin/users/u1/block', {
        is_usage_blocked: true,
        blocked_reason: 'usage_limits.edit.default_block_reason',
      })
    );
    expect(await screen.findByRole('button', { name: UNBLOCK })).toBeInTheDocument();
  });

  it('unblocks a blocked user with a null reason', async () => {
    get.mockResolvedValue(listOf([makeUsageLimitsUser({ is_usage_blocked: true })]));
    const { user } = render();
    await user.click(await screen.findByRole('button', { name: UNBLOCK }));
    await waitFor(() =>
      expect(put).toHaveBeenCalledWith('/usage-limits/admin/users/u1/block', {
        is_usage_blocked: false,
        blocked_reason: null,
      })
    );
  });

  it('reverts the optimistic block when the server refuses', async () => {
    put.mockRejectedValue(new ApiError('nope', 500));
    const { user } = render();
    await user.click(await screen.findByRole('button', { name: BLOCK }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('usage_limits.edit.error'));
    // Reverted: the row is unblocked again, so the block affordance is back.
    expect(await screen.findByRole('button', { name: BLOCK })).toBeInTheDocument();
  });
});

describe('AdminUsageLimitsSection — edit modal', () => {
  it('opens the modal for the chosen row and merges the saved row back in', async () => {
    const { user } = render();
    await user.click(await screen.findByRole('button', { name: 'usage_limits.table.edit' }));
    expect(await screen.findByText('modal-for:a@b.co')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'stub-save' }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('usage_limits.edit.success'));
    // The merged row replaced the old one without a refetch.
    expect(await screen.findByText('merged@example.com')).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(1);
  });
});

describe('AdminUsageLimitsSection — querying', () => {
  it('refetches sorted by email when its header is clicked', async () => {
    const { user } = render();
    await screen.findByText('a@b.co');
    await user.click(screen.getByRole('columnheader', { name: /table\.email/ }));
    await waitFor(() =>
      expect(get).toHaveBeenLastCalledWith(
        '/usage-limits/admin/users',
        expect.objectContaining({
          params: expect.objectContaining({ sort_by: 'email', sort_order: 'asc' }),
        })
      )
    );
  });

  it('refetches with the debounced search term', async () => {
    const { user } = render();
    await screen.findByText('a@b.co');
    await user.type(screen.getByPlaceholderText('usage_limits.search_placeholder'), 'alice');
    await waitFor(
      () =>
        expect(get).toHaveBeenLastCalledWith(
          '/usage-limits/admin/users',
          expect.objectContaining({ params: expect.objectContaining({ search: 'alice' }) })
        ),
      { timeout: 2000 }
    );
  });
});
