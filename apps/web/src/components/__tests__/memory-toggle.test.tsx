/**
 * MemoryToggle — the enabled/disabled affordance, the optimistic PATCH + refresh
 * + toast on success, the error toast, and the no-user disabled guard.
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

import { MemoryToggle } from '../memory-toggle';

function authed(over: Partial<User> = {}) {
  return { user: makeUser(over), refreshUser: vi.fn() };
}

beforeEach(() => {
  vi.clearAllMocks();
  patch.mockResolvedValue({});
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('MemoryToggle', () => {
  it('offers to disable memory when it is enabled', () => {
    useAuth.mockReturnValue(authed({ memory_enabled: true }));
    renderWithProviders(<MemoryToggle />);
    expect(screen.getByRole('button', { name: 'memory.toggle.disable' })).toBeInTheDocument();
  });

  it('offers to enable memory when it is disabled', () => {
    useAuth.mockReturnValue(authed({ memory_enabled: false }));
    renderWithProviders(<MemoryToggle />);
    expect(screen.getByRole('button', { name: 'memory.toggle.enable' })).toBeInTheDocument();
  });

  it('persists the toggled value, refreshes the user and toasts on success', async () => {
    const ctx = authed({ memory_enabled: true });
    useAuth.mockReturnValue(ctx);
    const { user } = renderWithProviders(<MemoryToggle />);
    await user.click(screen.getByRole('button'));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/auth/me/memory-preference', { memory_enabled: false })
    );
    expect(ctx.refreshUser).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledTimes(1);
  });

  it('shows an error toast when the update fails', async () => {
    patch.mockRejectedValue(new Error('boom'));
    useAuth.mockReturnValue(authed());
    const { user } = renderWithProviders(<MemoryToggle />);
    await user.click(screen.getByRole('button'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
  });

  it('is disabled when no user is authenticated', () => {
    useAuth.mockReturnValue({ user: null, refreshUser: vi.fn() });
    renderWithProviders(<MemoryToggle />);
    expect(screen.getByRole('button')).toBeDisabled();
  });
});
