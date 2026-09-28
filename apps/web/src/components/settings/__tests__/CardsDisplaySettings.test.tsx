/**
 * CardsDisplaySettings — the four response display modes, selecting one
 * (persist + refresh + toast), the same-mode no-op, and the error toast.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { act, renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
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
  it('renders the four display modes and announces the selected one', () => {
    useAuth.mockReturnValue(authed());
    renderWithProviders(<CardsDisplaySettings lng="en" />);
    for (const m of ['cards', 'html', 'html_cards', 'markdown']) {
      expect(screen.getByRole('button', { name: MODE(m) })).toHaveAttribute(
        'aria-pressed',
        String(m === 'cards')
      );
    }
  });

  it.each(['html', 'html_cards', 'markdown'])(
    'selecting %s persists it, refreshes and toasts',
    async mode => {
      const ctx = authed({ response_display_mode: 'cards' });
      useAuth.mockReturnValue(ctx);
      const { user } = renderWithProviders(<CardsDisplaySettings lng="en" />);
      await user.click(screen.getByRole('button', { name: MODE(mode) }));
      await waitFor(() =>
        expect(patch).toHaveBeenCalledWith('/auth/me/display-mode-preference', {
          response_display_mode: mode,
        })
      );
      expect(ctx.refreshUser).toHaveBeenCalled();
      expect(toast.success).toHaveBeenCalledTimes(1);
    }
  );

  it('preserves focus while saving the combined mode and ignores duplicate clicks', async () => {
    const request = Promise.withResolvers<object>();
    patch.mockReturnValue(request.promise);
    useAuth.mockReturnValue(authed());
    const { user } = renderWithProviders(<CardsDisplaySettings lng="en" />);
    const combined = screen.getByRole('button', { name: MODE('html_cards') });
    await user.click(combined);
    expect(combined).toHaveFocus();
    expect(combined).toHaveAttribute('aria-disabled', 'true');
    await user.click(combined);
    expect(patch).toHaveBeenCalledTimes(1);
    await act(async () => request.resolve({}));
    expect(combined).toHaveFocus();
    expect(combined).toHaveAttribute('aria-disabled', 'false');
  });

  it.each(['cards', 'html', 'html_cards', 'markdown'])(
    're-selecting the active mode %s is a no-op',
    async mode => {
      useAuth.mockReturnValue(authed({ response_display_mode: mode }));
      const { user } = renderWithProviders(<CardsDisplaySettings lng="en" />);
      await user.click(screen.getByRole('button', { name: MODE(mode) }));
      expect(patch).not.toHaveBeenCalled();
    }
  );

  it.each(['markdown', 'html_cards'])(
    'keeps the previous mode after a failed %s update and allows retry',
    async mode => {
      patch.mockRejectedValueOnce(new Error('boom'));
      const ctx = authed({ response_display_mode: 'cards' });
      useAuth.mockReturnValue(ctx);
      const { user } = renderWithProviders(<CardsDisplaySettings lng="en" />);
      const option = screen.getByRole('button', { name: MODE(mode) });
      await user.click(option);
      await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
      expect(screen.getByRole('button', { name: MODE('cards') })).toHaveAttribute(
        'aria-pressed',
        'true'
      );
      expect(option).toHaveAttribute('aria-pressed', 'false');
      expect(ctx.refreshUser).not.toHaveBeenCalled();
      await user.click(option);
      await waitFor(() => expect(ctx.refreshUser).toHaveBeenCalledTimes(1));
      expect(toast.success).toHaveBeenCalledTimes(1);
    }
  );
});
