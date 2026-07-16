/**
 * UserDebugSettings — the debug-panel toggle (persist + refresh + toast, and the
 * error toast).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
const { patch } = vi.hoisted(() => ({ patch: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { patch } }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { UserDebugSettings } from '../UserDebugSettings';

beforeEach(() => {
  vi.clearAllMocks();
  patch.mockResolvedValue({});
});

describe('UserDebugSettings', () => {
  it('enabling the debug panel persists, refreshes and toasts', async () => {
    const refreshUser = vi.fn();
    useAuth.mockReturnValue({ user: { id: 'u1', debug_panel_enabled: false }, refreshUser });
    const { user } = renderWithProviders(<UserDebugSettings lng="en" collapsible={false} />);
    await user.click(screen.getByRole('switch'));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/auth/me/debug-panel-preference', {
        debug_panel_enabled: true,
      })
    );
    expect(refreshUser).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledTimes(1);
  });

  it('toasts an error when the update fails', async () => {
    patch.mockRejectedValue(new Error('boom'));
    useAuth.mockReturnValue({
      user: { id: 'u1', debug_panel_enabled: false },
      refreshUser: vi.fn(),
    });
    const { user } = renderWithProviders(<UserDebugSettings lng="en" collapsible={false} />);
    await user.click(screen.getByRole('switch'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
  });
});
