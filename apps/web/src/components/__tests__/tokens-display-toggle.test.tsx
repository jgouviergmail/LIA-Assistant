/**
 * TokensDisplayToggle — enabled/disabled affordance, PATCH + refresh
 * + toast, error toast, and the no-user disabled guard.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { makeUser } from '@/__tests__/factories';
import type { User } from '@/lib/auth';
import { ICON_STYLES } from '@/lib/icon-style';
import { IconStyleContext } from '@/lib/icon-style-context';

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
  it.each(ICON_STYLES)('keeps the saved toggle state visible with %s icons', async style => {
    const ctx = authed({ tokens_display_enabled: false });
    ctx.refreshUser.mockImplementation(async () => {
      ctx.user = { ...ctx.user, tokens_display_enabled: !ctx.user.tokens_display_enabled };
    });
    useAuth.mockReturnValue(ctx);
    const { user } = renderWithProviders(
      <IconStyleContext.Provider value={style}>
        <TokensDisplayToggle />
      </IconStyleContext.Provider>
    );
    const button = screen.getByRole('button', { name: 'tokens_display.toggle.enable' });
    expect(button).toHaveAttribute('aria-pressed', 'false');
    expect(button).not.toHaveClass('border-primary', 'bg-primary/10');
    expect(button.querySelector('svg')).toHaveAttribute('data-icon-style', style);
    await user.tab();
    expect(button).toHaveFocus();
    expect(button).toHaveClass('focus-visible:ring-2');
    await user.keyboard('{Enter}');
    await waitFor(() => expect(button).toHaveAttribute('aria-pressed', 'true'));
    expect(patch).toHaveBeenLastCalledWith('/auth/me/tokens-display-preference', {
      tokens_display_enabled: true,
    });
    expect(button).toHaveAccessibleName('tokens_display.toggle.disable');
    expect(button).toHaveClass(
      'border-primary',
      'bg-primary/10',
      'dark:bg-[color-mix(in_srgb,var(--color-card)_75%,black)]'
    );

    await user.click(button);
    await waitFor(() => expect(button).toHaveAttribute('aria-pressed', 'false'));
    expect(patch).toHaveBeenLastCalledWith('/auth/me/tokens-display-preference', {
      tokens_display_enabled: false,
    });
    expect(button).not.toHaveClass('border-primary', 'bg-primary/10');
    expect(ctx.refreshUser).toHaveBeenCalledTimes(2);
  });

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
