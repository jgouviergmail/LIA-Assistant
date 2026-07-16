/**
 * TokensDisplayToggle — enabled/disabled affordance, optimistic PATCH + refresh
 * + toast, error toast, and the no-user disabled guard.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { makeUser } from '@/__tests__/factories';
import type { User } from '@/lib/auth';

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
const { patch } = vi.hoisted(() => ({ patch: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { patch } }));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import { TokensDisplayToggle } from '../tokens-display-toggle';

function authed(over: Partial<User> = {}) {
  return { user: makeUser(over), refreshUser: vi.fn() };
}

beforeEach(() => {
  vi.clearAllMocks();
  patch.mockResolvedValue({});
});

describe('TokensDisplayToggle', () => {
  it('offers to enable the token display when it is off', () => {
    useAuth.mockReturnValue(authed({ tokens_display_enabled: false }));
    renderWithProviders(<TokensDisplayToggle />);
    expect(
      screen.getByRole('button', { name: 'tokens_display.toggle.enable' })
    ).toBeInTheDocument();
  });

  it('persists the enabled value and toasts on success', async () => {
    const ctx = authed({ tokens_display_enabled: false });
    useAuth.mockReturnValue(ctx);
    const { user } = renderWithProviders(<TokensDisplayToggle />);
    await user.click(screen.getByRole('button'));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/auth/me/tokens-display-preference', {
        tokens_display_enabled: true,
      })
    );
    expect(ctx.refreshUser).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledTimes(1);
  });

  it('shows an error toast when the update fails', async () => {
    patch.mockRejectedValue(new Error('boom'));
    useAuth.mockReturnValue(authed());
    const { user } = renderWithProviders(<TokensDisplayToggle />);
    await user.click(screen.getByRole('button'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
  });

  it('is disabled when no user is authenticated', () => {
    useAuth.mockReturnValue({ user: null, refreshUser: vi.fn() });
    renderWithProviders(<TokensDisplayToggle />);
    expect(screen.getByRole('button')).toBeDisabled();
  });
});
