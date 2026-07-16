/**
 * ExecutionModeToggle — the react/pipeline affordance, the optimistic PATCH +
 * refresh + toast, the error toast, and the no-user disabled guard.
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

import { ExecutionModeToggle } from '../execution-mode-toggle';

function authed(over: Partial<User> = {}) {
  return { user: makeUser(over), refreshUser: vi.fn() };
}

beforeEach(() => {
  vi.clearAllMocks();
  patch.mockResolvedValue({});
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('ExecutionModeToggle', () => {
  it('offers to switch to react when in pipeline mode', () => {
    useAuth.mockReturnValue(authed({ execution_mode: 'pipeline' }));
    renderWithProviders(<ExecutionModeToggle />);
    expect(
      screen.getByRole('button', { name: 'executionMode.toggle.enable_react' })
    ).toBeInTheDocument();
  });

  it('offers to switch to pipeline when in react mode', () => {
    useAuth.mockReturnValue(authed({ execution_mode: 'react' }));
    renderWithProviders(<ExecutionModeToggle />);
    expect(
      screen.getByRole('button', { name: 'executionMode.toggle.enable_pipeline' })
    ).toBeInTheDocument();
  });

  it('switches pipeline → react, refreshes and toasts on success', async () => {
    const ctx = authed({ execution_mode: 'pipeline' });
    useAuth.mockReturnValue(ctx);
    const { user } = renderWithProviders(<ExecutionModeToggle />);
    await user.click(screen.getByRole('button'));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/auth/me/execution-mode-preference', {
        execution_mode: 'react',
      })
    );
    expect(ctx.refreshUser).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledTimes(1);
  });

  it('shows an error toast when the update fails', async () => {
    patch.mockRejectedValue(new Error('boom'));
    useAuth.mockReturnValue(authed());
    const { user } = renderWithProviders(<ExecutionModeToggle />);
    await user.click(screen.getByRole('button'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
  });

  it('is disabled when no user is authenticated', () => {
    useAuth.mockReturnValue({ user: null, refreshUser: vi.fn() });
    renderWithProviders(<ExecutionModeToggle />);
    expect(screen.getByRole('button')).toBeDisabled();
  });
});
