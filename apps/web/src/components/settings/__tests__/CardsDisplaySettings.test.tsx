/**
 * CardsDisplaySettings — the three response display modes, selecting one
 * (persist + refresh + toast), the same-mode no-op, and the error toast.
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

import { CardsDisplaySettings } from '../CardsDisplaySettings';

const MODE = (m: string) => `settings.preferences.display_mode.modes.${m}.label`;

function authed(over: Partial<User> = {}) {
  return { user: makeUser({ response_display_mode: 'cards', ...over }), refreshUser: vi.fn() };
}

beforeEach(() => {
  vi.clearAllMocks();
  patch.mockResolvedValue({});
});

describe('CardsDisplaySettings', () => {
  it('renders the three display modes', () => {
    useAuth.mockReturnValue(authed());
    renderWithProviders(<CardsDisplaySettings lng="en" />);
    for (const m of ['cards', 'html', 'markdown']) {
      expect(screen.getByRole('button', { name: MODE(m) })).toBeInTheDocument();
    }
  });

  it('selecting a different mode persists it, refreshes and toasts', async () => {
    const ctx = authed({ response_display_mode: 'cards' });
    useAuth.mockReturnValue(ctx);
    const { user } = renderWithProviders(<CardsDisplaySettings lng="en" />);
    await user.click(screen.getByRole('button', { name: MODE('html') }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/auth/me/display-mode-preference', {
        response_display_mode: 'html',
      })
    );
    expect(ctx.refreshUser).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledTimes(1);
  });

  it('re-selecting the active mode is a no-op', async () => {
    useAuth.mockReturnValue(authed({ response_display_mode: 'cards' }));
    const { user } = renderWithProviders(<CardsDisplaySettings lng="en" />);
    await user.click(screen.getByRole('button', { name: MODE('cards') }));
    expect(patch).not.toHaveBeenCalled();
  });

  it('shows an error toast when the update fails', async () => {
    patch.mockRejectedValue(new Error('boom'));
    useAuth.mockReturnValue(authed({ response_display_mode: 'cards' }));
    const { user } = renderWithProviders(<CardsDisplaySettings lng="en" />);
    await user.click(screen.getByRole('button', { name: MODE('markdown') }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
  });
});
