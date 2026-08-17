/**
 * DocumentGenerationSettings — the single per-user opt-in toggle (ADR-226):
 * reflects the stored preference, persists + refreshes + toasts on change,
 * reports the failed update, and never fires without an authenticated user.
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

import { DocumentGenerationSettings } from '../DocumentGenerationSettings';

function authed(over: Partial<User> = {}) {
  return { user: makeUser(over), refreshUser: vi.fn() };
}

beforeEach(() => {
  vi.clearAllMocks();
  patch.mockResolvedValue({});
  useAuth.mockReturnValue(authed());
});

describe('DocumentGenerationSettings — opt-in toggle', () => {
  it('reflects the stored preference', () => {
    useAuth.mockReturnValue(authed({ document_generation_enabled: false }));
    renderWithProviders(<DocumentGenerationSettings lng="en" collapsible={false} />);
    expect(screen.getByRole('switch')).not.toBeChecked();
  });

  it('enabling generation persists it, refreshes and toasts', async () => {
    const ctx = authed({ document_generation_enabled: false });
    useAuth.mockReturnValue(ctx);
    const { user } = renderWithProviders(
      <DocumentGenerationSettings lng="en" collapsible={false} />
    );
    await user.click(screen.getByRole('switch'));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/users/u1', { document_generation_enabled: true })
    );
    expect(ctx.refreshUser).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledTimes(1);
  });

  it('toasts an error when the update fails', async () => {
    patch.mockRejectedValue(new Error('boom'));
    const { user } = renderWithProviders(
      <DocumentGenerationSettings lng="en" collapsible={false} />
    );
    await user.click(screen.getByRole('switch'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
  });

  it('does not persist when no user is authenticated', async () => {
    useAuth.mockReturnValue({ user: null, refreshUser: vi.fn() });
    const { user } = renderWithProviders(
      <DocumentGenerationSettings lng="en" collapsible={false} />
    );
    await user.click(screen.getByRole('switch'));
    expect(patch).not.toHaveBeenCalled();
  });
});
