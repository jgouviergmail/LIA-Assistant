/**
 * AdminUsageLimitsEditModal — saving a user's usage limits (PUT), the extra
 * block PUT only when the block state changes, the error path (no onSave), and
 * cancel.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { put } = vi.hoisted(() => ({ put: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ apiClient: { put } }));
const { toast } = vi.hoisted(() => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import { AdminUsageLimitsEditModal } from '../AdminUsageLimitsEditModal';
// Shared domain factory — the same row shape is exercised by
// AdminUsageLimitsSection.test.tsx.
import { makeUsageLimitsUser as makeUser } from '@/__tests__/factories';

const save = () => screen.getByRole('button', { name: 'usage_limits.edit.save' });

beforeEach(() => {
  vi.clearAllMocks();
  put.mockResolvedValue(makeUser());
});

describe('AdminUsageLimitsEditModal', () => {
  it('renders the modal titled for the target user when open', () => {
    renderWithProviders(
      <AdminUsageLimitsEditModal user={makeUser()} open onClose={vi.fn()} onSave={vi.fn()} />
    );
    expect(screen.getByText('usage_limits.edit.title')).toBeInTheDocument();
  });

  it('saving the unchanged limits issues a single limits PUT and reports back', async () => {
    const onSave = vi.fn();
    const { user } = renderWithProviders(
      <AdminUsageLimitsEditModal user={makeUser()} open onClose={vi.fn()} onSave={onSave} />
    );
    await user.click(save());
    await waitFor(() =>
      expect(put).toHaveBeenCalledWith('/usage-limits/admin/users/u1/limits', {
        token_limit_per_cycle: 1000,
        message_limit_per_cycle: 50,
        cost_limit_per_cycle: 5,
        token_limit_absolute: null,
        message_limit_absolute: null,
        cost_limit_absolute: null,
      })
    );
    expect(put).toHaveBeenCalledTimes(1);
    expect(onSave).toHaveBeenCalled();
  });

  it('issues an additional block PUT when the block state changes', async () => {
    const { user } = renderWithProviders(
      <AdminUsageLimitsEditModal
        user={makeUser({ is_usage_blocked: false })}
        open
        onClose={vi.fn()}
        onSave={vi.fn()}
      />
    );
    await user.click(screen.getByRole('switch', { name: 'usage_limits.edit.block_user' }));
    await user.click(save());
    await waitFor(() =>
      expect(put).toHaveBeenCalledWith('/usage-limits/admin/users/u1/block', {
        is_usage_blocked: true,
        blocked_reason: null,
      })
    );
    expect(put).toHaveBeenCalledTimes(2);
  });

  it('toasts an error and does not report success when saving fails', async () => {
    put.mockRejectedValue(new Error('boom'));
    const onSave = vi.fn();
    const { user } = renderWithProviders(
      <AdminUsageLimitsEditModal user={makeUser()} open onClose={vi.fn()} onSave={onSave} />
    );
    await user.click(save());
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
    expect(onSave).not.toHaveBeenCalled();
  });

  it('closes without saving on cancel', async () => {
    const onClose = vi.fn();
    const { user } = renderWithProviders(
      <AdminUsageLimitsEditModal user={makeUser()} open onClose={onClose} onSave={vi.fn()} />
    );
    await user.click(screen.getByRole('button', { name: 'usage_limits.edit.cancel' }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(put).not.toHaveBeenCalled();
  });
});
